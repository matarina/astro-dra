"""Generic evidence coverage planning under a bounded context budget.

This module plans candidate evidence coverage only. It never decides support,
entailment, correction, or publication status. Candidates retain source identity
and exact offsets so the writer and later adjudicator can resolve every passage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CoverageCandidate:
    source_id: str | int | None
    start: int
    end: int
    text: str
    fields: tuple[str, ...] = ()
    score: float = 0.0
    section: str = ""
    method: str = "candidate"
    lexical_match: bool = False
    ranker_score: float | None = None

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def key(self) -> tuple[str, int, int]:
        return (str(self.source_id), int(self.start), int(self.end))


@dataclass(frozen=True)
class CoveragePlan:
    selected: tuple[CoverageCandidate, ...]
    required_fields: tuple[str, ...]
    covered_fields: tuple[str, ...]
    uncovered_fields: tuple[str, ...]
    source_ids: tuple[str, ...]
    context_chars: int
    context_sha256: str

    @property
    def complete(self) -> bool:
        return not self.uncovered_fields


def _deduplicate(candidates: Iterable[CoverageCandidate]) -> list[CoverageCandidate]:
    out: dict[tuple[str, int, int], CoverageCandidate] = {}
    for candidate in candidates:
        if candidate.end <= candidate.start or not candidate.text:
            continue
        fields = tuple(dict.fromkeys(str(f) for f in candidate.fields if str(f)))
        normalized = CoverageCandidate(
            source_id=candidate.source_id,
            start=int(candidate.start), end=int(candidate.end), text=str(candidate.text),
            fields=fields, score=float(candidate.score), section=str(candidate.section or ""),
            method=str(candidate.method or "candidate"),
            lexical_match=bool(candidate.lexical_match),
            ranker_score=(float(candidate.ranker_score)
                          if candidate.ranker_score is not None else None),
        )
        previous = out.get(normalized.key)
        if previous is None or normalized.score > previous.score:
            out[normalized.key] = normalized
    return list(out.values())


def plan_coverage(
    candidates: Sequence[CoverageCandidate],
    required_fields: Sequence[str],
    *,
    context_chars: int,
    min_sources: int = 0,
    max_items: int | None = None,
) -> CoveragePlan:
    """Greedily maximize uncovered-field and source coverage under a byte budget.

    The gain ordering is explicit: an uncovered requested field, then a new
    source, then the candidate score. This prevents a dense cluster from
    consuming the whole budget while another requested field remains unseen.
    ``score`` is a relevance hint only and is never an evidence verdict.
    """
    if context_chars < 0:
        raise ValueError("context_chars must be non-negative")
    required = tuple(dict.fromkeys(str(field) for field in required_fields if str(field)))
    available = _deduplicate(candidates)
    selected: list[CoverageCandidate] = []
    covered: set[str] = set()
    sources: set[str] = set()
    used = 0
    limit = max_items if max_items is None else max(0, int(max_items))

    while available and used < context_chars and (limit is None or len(selected) < limit):
        ranked = []
        for candidate in available:
            if used + candidate.chars > context_chars:
                continue
            new_fields = set(candidate.fields) - covered
            new_source = str(candidate.source_id) not in sources
            # A source bonus remains active until the declared diversity floor
            # is met, then relevance breaks ties among equivalent coverage.
            source_gain = 1 if new_source and len(sources) < min_sources else 0
            ranked.append((len(new_fields), source_gain, float(candidate.score),
                           -candidate.start, candidate))
        if not ranked:
            break
        _, _, _, _, chosen = max(ranked, key=lambda row: row[:4])
        selected.append(chosen)
        used += chosen.chars
        covered.update(chosen.fields)
        sources.add(str(chosen.source_id))
        available.remove(chosen)

    ordered = tuple(sorted(selected, key=lambda item: (str(item.source_id), item.start, item.end)))
    context = "\n\n".join(item.text for item in ordered)
    covered_fields = tuple(field for field in required if field in covered)
    uncovered_fields = tuple(field for field in required if field not in covered)
    return CoveragePlan(
        selected=ordered,
        required_fields=required,
        covered_fields=covered_fields,
        uncovered_fields=uncovered_fields,
        source_ids=tuple(sorted({str(item.source_id) for item in ordered})),
        context_chars=len(context),
        context_sha256=hashlib.sha256(context.encode()).hexdigest(),
    )


# Opt-in structural candidate API. The legacy planner above is intentionally
# unchanged; no writer or report path calls these helpers implicitly.
@dataclass(frozen=True)
class StructureHeading:
    start: int
    end: int
    level: int
    title: str


@dataclass(frozen=True)
class StructureParagraph:
    start: int
    end: int
    section_id: int | None
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class SourceStructure:
    source_id: str | int | None
    text: str
    sha256: str
    paragraphs: tuple[StructureParagraph, ...]
    headings: tuple[StructureHeading, ...] = ()


@dataclass(frozen=True)
class ParagraphBundle:
    source: SourceStructure
    first: int
    last: int
    fields: tuple[str, ...]
    seeds: tuple[int, ...]
    within_bundle_limit: bool = True
    seed_fields: tuple[tuple[int, tuple[str, ...]], ...] = ()

    @property
    def start(self) -> int:
        return self.source.paragraphs[self.first].start

    @property
    def end(self) -> int:
        return self.source.paragraphs[self.last].end

    @property
    def text(self) -> str:
        return self.source.text[self.start:self.end]


@dataclass(frozen=True)
class ParagraphBundlePlan:
    selected: tuple[ParagraphBundle, ...]
    context: str
    context_chars: int
    budget_chars: int
    context_sha256: str
    receipts: tuple[dict, ...]


def index_source_structure(
    text: str, *, source_id: str | int | None = None,
    headings: Sequence[StructureHeading] | None = None,
) -> SourceStructure:
    """Index exact paragraph slices and generic heading paths, without ranking.

    Accept acquisition-provided heading offsets or recognize Markdown ATX and
    setext markup (in any language). Unmarked prose stays structurally unknown;
    no heading vocabulary is inferred. Repeated titles have distinct section IDs.
    """
    import re

    if headings is None:
        found = []
        lines = text.splitlines(keepends=True)
        offsets = []
        offset = 0
        for line in lines:
            offsets.append(offset)
            offset += len(line)
        fence = None
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\r\n')
            marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                i += 1
                continue
            if fence is not None:
                i += 1
                continue
            atx = re.match(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*$', line)
            if atx:
                title = re.sub(r'[ \t]+#+[ \t]*$', '', atx.group(2))
                found.append(StructureHeading(offsets[i], offsets[i] + len(lines[i]),
                                              len(atx.group(1)), title))
            elif line.strip() and i + 1 < len(lines):
                underline = re.fullmatch(r' {0,3}(=+|-+)[ \t]*', lines[i + 1].rstrip('\r\n'))
                if underline:
                    found.append(StructureHeading(
                        offsets[i], offsets[i + 1] + len(lines[i + 1]),
                        1 if underline.group(1)[0] == '=' else 2, line.strip()))
                    i += 1
            i += 1
        headings = found
    ordered = sorted(headings, key=lambda h: h.start)
    previous_end = 0
    for heading in ordered:
        if (type(heading.start) is not int or type(heading.end) is not int
                or type(heading.level) is not int or heading.level < 1
                or not previous_end <= heading.start < heading.end <= len(text)):
            raise ValueError('invalid or overlapping heading offsets')
        raw_title = text[heading.start:heading.end].splitlines()[0].strip()
        raw_title = re.sub(r'^#{1,6}[ \t]+', '', raw_title)
        raw_title = re.sub(r'[ \t]+#+[ \t]*$', '', raw_title)
        if raw_title != heading.title:
            raise ValueError('heading title does not match canonical source slice')
        previous_end = heading.end
    paragraphs = []
    stack: list[StructureHeading] = []

    def append_paragraphs(start: int, end: int):
        segment = text[start:end]
        # Blank lines delimit paragraphs; whitespace is excluded only at edges.
        cursor = 0
        for boundary in list(re.finditer(r'\r?\n[ \t]*\r?\n', segment)) + [None]:
            finish = boundary.start() if boundary is not None else len(segment)
            raw = segment[cursor:finish]
            begin = cursor + len(raw) - len(raw.lstrip())
            finish = cursor + len(raw.rstrip())
            if begin < finish:
                paragraphs.append(StructureParagraph(
                    start + begin, start + finish,
                    stack[-1].start if stack else None,
                    tuple(h.title for h in stack)))
            cursor = boundary.end() if boundary is not None else len(segment)

    cursor = 0
    for heading in ordered:
        append_paragraphs(cursor, heading.start)
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
        cursor = heading.end
    append_paragraphs(cursor, len(text))
    return SourceStructure(source_id, text, hashlib.sha256(text.encode()).hexdigest(),
                           tuple(paragraphs), tuple(ordered))


def generate_paragraph_bundles(
    source: SourceStructure, seed_fields: dict[int, Sequence[str]], *,
    adjacent_paragraphs: int = 1, max_bundle_chars: int = 6000,
) -> tuple[ParagraphBundle, ...]:
    """Expand supplied seeds without a relevance rule or shortlist.

    Every indexed paragraph is available to the caller before seed selection.
    Options contain whole adjacent paragraphs in one local section; two remote
    seeds remain separate options. Oversized seeds remain visible but ineligible,
    so their omission is receipted instead of silently truncating a paragraph.
    """
    _validate_source_structure(source)
    if adjacent_paragraphs < 0 or max_bundle_chars < 1:
        raise ValueError('invalid bundle bounds')
    normalized = {}
    for index, fields in seed_fields.items():
        if type(index) is not int or not 0 <= index < len(source.paragraphs):
            raise ValueError('seed paragraph index out of range')
        normalized[index] = tuple(sorted({str(f) for f in fields if str(f)}))
    extents = set()
    for index in normalized:
        section = source.paragraphs[index].section_id
        left = right = index
        for _ in range(adjacent_paragraphs):
            if left > 0 and source.paragraphs[left - 1].section_id == section:
                left -= 1
            if right + 1 < len(source.paragraphs) and source.paragraphs[right + 1].section_id == section:
                right += 1
        for first in range(left, index + 1):
            for last in range(index, right + 1):
                size = source.paragraphs[last].end - source.paragraphs[first].start
                if size <= max_bundle_chars or first == last == index:
                    extents.add((first, last))
    bundles = []
    for first, last in sorted(extents):
        seeds = tuple(i for i in sorted(normalized) if first <= i <= last)
        fields = tuple(sorted({f for i in seeds for f in normalized[i]}))
        size = source.paragraphs[last].end - source.paragraphs[first].start
        bundles.append(ParagraphBundle(source, first, last, fields, seeds,
                                       size <= max_bundle_chars,
                                       tuple((i, normalized[i]) for i in seeds)))
    return tuple(bundles)


def _validate_source_structure(source: SourceStructure) -> None:
    """Rebind public structural objects to their canonical acquired text."""
    if hashlib.sha256(source.text.encode()).hexdigest() != source.sha256:
        raise ValueError('source SHA does not match canonical source text')
    canonical = index_source_structure(source.text, source_id=source.source_id,
                                       headings=source.headings)
    if canonical.paragraphs != source.paragraphs:
        raise ValueError('paragraph offsets/sections do not match canonical source text')


def _validated_bundle(
    bundle: ParagraphBundle, canonical_sources: Sequence[SourceStructure] | None = None,
) -> ParagraphBundle:
    from dataclasses import replace

    _validate_source_structure(bundle.source)
    if canonical_sources is not None:
        matches = [source for source in canonical_sources
                   if source.source_id == bundle.source.source_id]
        if len(matches) != 1 or matches[0] != bundle.source:
            raise ValueError('bundle differs from caller canonical source binding')
        _validate_source_structure(matches[0])
    if (type(bundle.first) is not int or type(bundle.last) is not int
            or not 0 <= bundle.first <= bundle.last < len(bundle.source.paragraphs)):
        raise ValueError('invalid bundle paragraph bounds')
    paragraphs = bundle.source.paragraphs[bundle.first:bundle.last + 1]
    if any(p.section_id != paragraphs[0].section_id for p in paragraphs):
        raise ValueError('bundle crosses a canonical section boundary')
    if not 0 <= bundle.start < bundle.end <= len(bundle.source.text):
        raise ValueError('invalid canonical bundle offsets')
    if bundle.text != bundle.source.text[bundle.start:bundle.end]:
        raise ValueError('bundle text does not match canonical source slice')
    memberships: dict[int, set[str]] = {}
    for seed, fields in bundle.seed_fields:
        if type(seed) is not int or not bundle.first <= seed <= bundle.last:
            raise ValueError('invalid bundle seed offsets')
        memberships.setdefault(seed, set()).update(str(f) for f in fields if str(f))
    fields = tuple(sorted({str(f) for f in bundle.fields if str(f)}))
    seeds = tuple(sorted(set(bundle.seeds)))
    if seeds != tuple(sorted(memberships)) or set(fields) != {
            f for fs in memberships.values() for f in fs}:
        raise ValueError('bundle field/seed memberships inconsistent')
    return replace(bundle, fields=fields, seeds=seeds,
                   seed_fields=tuple((i, tuple(sorted(fs)))
                                     for i, fs in sorted(memberships.items())))


def _merge_bundles(bundles: Sequence[ParagraphBundle]) -> tuple[ParagraphBundle, ...]:
    """Union overlapping extents only, never concatenate across a gap."""
    from dataclasses import replace

    merged: list[ParagraphBundle] = []
    # Source IDs never influence allocation/order; content hashes break ties.
    for bundle in sorted(bundles, key=lambda b: (b.source.sha256, b.start, b.end)):
        while True:
            match = next((i for i, old in enumerate(merged)
                          if old.source == bundle.source
                          and old.source.paragraphs[old.first].section_id
                          == bundle.source.paragraphs[bundle.first].section_id
                          and old.first <= bundle.last and bundle.first <= old.last), None)
            if match is None:
                break
            old = merged.pop(match)
            memberships: dict[int, set[str]] = {}
            for seed, fields in (*old.seed_fields, *bundle.seed_fields):
                memberships.setdefault(seed, set()).update(fields)
            bundle = replace(bundle, first=min(old.first, bundle.first),
                             last=max(old.last, bundle.last),
                             fields=tuple(sorted(set(old.fields) | set(bundle.fields))),
                             seeds=tuple(sorted(set(old.seeds) | set(bundle.seeds))),
                             seed_fields=tuple((i, tuple(sorted(fs)))
                                               for i, fs in sorted(memberships.items())))
        merged.append(bundle)
    return tuple(sorted(merged, key=lambda b: (b.source.sha256, b.start, b.end)))


def serialize_paragraph_bundles(
    bundles: Sequence[ParagraphBundle], *,
    canonical_sources: Sequence[SourceStructure] | None = None,
) -> str:
    """The budgeted candidate wire format, including all metadata/separators."""
    import json

    cards = []
    for raw_bundle in bundles:
        bundle = _validated_bundle(raw_bundle, canonical_sources)
        paragraph = bundle.source.paragraphs[bundle.first]
        metadata = dict(source_id=bundle.source.source_id,
                        source_sha256=bundle.source.sha256,
                        start=bundle.start, end=bundle.end,
                        heading_path=paragraph.heading_path,
                        structure='heading' if paragraph.section_id is not None else 'unknown',
                        fields=bundle.fields,
                        text_sha256=hashlib.sha256(bundle.text.encode()).hexdigest())
        cards.append(json.dumps(metadata, ensure_ascii=False, sort_keys=True) + '\n' + bundle.text)
    return '\n\n'.join(cards)


def plan_paragraph_bundles(
    candidates: Sequence[ParagraphBundle], *, context_chars: int,
    canonical_sources: Sequence[SourceStructure] | None = None,
) -> ParagraphBundlePlan:
    """Opt-in greedy structural packing using actual serialized character cost.

    Prefer new field/source pairs, then additional seed/paragraph coverage.
    Overlapping alternatives share one extent and union field memberships.
    This is bounded candidate availability, never support or a publication gate.
    """
    if context_chars < 0:
        raise ValueError('context_chars must be non-negative')
    candidates = tuple(_validated_bundle(b, canonical_sources) for b in candidates)
    selected: tuple[ParagraphBundle, ...] = ()
    remaining = list(candidates)
    while remaining:
        choices = []
        old_pairs = {(b.source.sha256, f) for b in selected for f in b.fields}
        old_paragraphs = {(b.source.sha256, i) for b in selected
                          for i in range(b.first, b.last + 1)}
        for index, candidate in enumerate(remaining):
            if not candidate.within_bundle_limit:
                continue
            proposed = _merge_bundles([*selected, candidate])
            # Do not let overlapping alternatives bypass their bundle cap by
            # manufacturing an extent not present in the generated candidate pool.
            if any(not any(b.source == c.source and b.first == c.first and b.last == c.last
                           and c.within_bundle_limit for c in candidates) for b in proposed):
                continue
            rendered = serialize_paragraph_bundles(proposed)
            if len(rendered) > context_chars:
                continue
            pairs = {(b.source.sha256, f) for b in proposed for f in b.fields}
            paragraphs = {(b.source.sha256, i) for b in proposed
                          for i in range(b.first, b.last + 1)}
            gain = (len(pairs - old_pairs), len(paragraphs - old_paragraphs))
            if gain == (0, 0):
                # Exact duplicate intervals may still contribute field labels.
                if proposed == selected:
                    continue
            choices.append((gain, -len(rendered), -index, proposed))
        if not choices:
            break
        _, _, neg_index, selected = max(choices, key=lambda row: row[:3])
        remaining.pop(-neg_index)
    context = serialize_paragraph_bundles(selected)
    receipts = []
    opportunities = {(b.source.sha256, b.source.source_id, seed, f): b.source
                     for b in candidates for seed, fields in b.seed_fields for f in fields}
    for (sha, source_id, seed, field), source in sorted(
            opportunities.items(), key=lambda item: (item[0][0], item[0][2], item[0][3])):
        attached = [b for b in selected if b.source == source
                    and b.first <= seed <= b.last and field in b.fields]
        paragraph = source.paragraphs[seed]
        section = {i for i, p in enumerate(source.paragraphs)
                   if p.section_id == paragraph.section_id}
        selected_indices = {i for b in attached for i in range(b.first, b.last + 1)}
        state = ('omitted' if not attached else
                 'planned' if paragraph.section_id is not None and section <= selected_indices
                 else 'partial')
        receipts.append(dict(source_id=source_id, source_sha256=sha, seed=seed, field=field,
                             field_sha256=hashlib.sha256(field.encode()).hexdigest(),
                             state=state, delivery_state='not_observed',
                             reason=('budget_or_bundle_limit' if not attached else
                                     'unknown_structure' if paragraph.section_id is None else
                                     'section_subset' if state == 'partial' else 'indexed_section'),
                             selected_offsets=[(b.start, b.end) for b in attached]))
    return ParagraphBundlePlan(selected, context, len(context), context_chars,
                               hashlib.sha256(context.encode()).hexdigest(), tuple(receipts))


def paragraph_bundle_delivery_receipts(
    plan: ParagraphBundlePlan, final_material: str, *,
    delivered_spans: Sequence[dict] = (),
    final_source_registry: Sequence[str | int | None] | None = None,
    canonical_sources: Sequence[SourceStructure] | None = None,
) -> tuple[dict, ...]:
    """Observe exact cards or explicitly bound formatter spans, never bare prose.

    A partial-delivery span binds source_id/source_sha256, source_start/end and
    material_start/end. Both slices must match exactly at those coordinates.
    Missing/invalid bindings cannot establish partial or exact attachment.
    """
    import json

    selected = tuple(_validated_bundle(b, canonical_sources) for b in plan.selected)
    canonical_context = serialize_paragraph_bundles(selected)
    if (plan.context != canonical_context or plan.context_chars != len(canonical_context)
            or plan.context_sha256 != hashlib.sha256(canonical_context.encode()).hexdigest()
            or not 0 <= plan.context_chars <= plan.budget_chars):
        raise ValueError('plan context/hash/budget does not match canonical serialization')
    registry = (None if final_source_registry is None else
                sorted({str(s) for s in final_source_registry}))
    registry_hash = (None if registry is None else
                     hashlib.sha256(json.dumps(registry, ensure_ascii=False).encode()).hexdigest())
    receipts = []
    for bundle in selected:
        card = serialize_paragraph_bundles([bundle])
        intervals = []
        invalid_spans = 0
        for span in delivered_spans:
            if (span.get('source_id') != bundle.source.source_id
                    or span.get('source_sha256') != bundle.source.sha256):
                continue
            a, b = span.get('source_start'), span.get('source_end')
            x, y = span.get('material_start'), span.get('material_end')
            if (not all(type(v) is int for v in (a, b, x, y))
                    or not bundle.start <= a < b <= bundle.end
                    or not 0 <= x < y <= len(final_material)
                    or final_material[x:y] != bundle.source.text[a:b]):
                invalid_spans += 1
                continue
            intervals.append((a, b))
        state = ('planned' if card in final_material else 'partial' if intervals else 'omitted')
        delivery = ('attached_exact' if state == 'planned' else
                    'partial_after_formatting' if intervals else 'omitted_after_formatting')
        registry_state = ('unknown' if registry is None else
                          'present' if str(bundle.source.source_id) in registry else 'registry_absent')
        if delivery == 'attached_exact' and registry_state == 'registry_absent':
            delivery = 'attached_text_registry_absent'
        receipts.append(dict(source_id=bundle.source.source_id,
                             source_sha256=bundle.source.sha256,
                             start=bundle.start, end=bundle.end, state=state,
                             delivery_state=delivery, registry_state=registry_state,
                             final_source_registry=registry, final_registry_sha256=registry_hash,
                             bound_delivered_offsets=sorted(set(intervals)),
                             invalid_delivery_spans=invalid_spans,
                             serialized_chars=len(card),
                             final_material_chars=len(final_material),
                             final_material_sha256=hashlib.sha256(final_material.encode()).hexdigest(),
                             text_sha256=hashlib.sha256(bundle.text.encode()).hexdigest()))
    return tuple(receipts)
