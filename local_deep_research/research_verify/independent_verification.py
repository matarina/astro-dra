"""Independent, source-only factual question answering.

This module is an isolated diagnostic stage.  It deliberately does not accept
the draft, a proposed answer, a verdict, or a repair instruction.  A caller
supplies neutral factual questions and the original source passages; the
returned answers retain source identity, exact quoted evidence, qualifiers,
counterevidence and explicit unknowns.  Nothing in this module edits a report
or decides whether a report claim should be deleted.

The stage is opt-in and has no dependency on the native report-review path.  It
can therefore be paired with the current writer/reviewer to distinguish a
failure to retrieve evidence from a failure to understand evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Iterable, Mapping


ANSWER_STATUSES = frozenset({"supported", "partial", "contradicted", "unknown"})


@dataclass(frozen=True)
class VerificationQuestion:
    """A neutral factual question, independent of a report claim."""

    question_id: str
    text: str
    source_ids: tuple[int, ...] = ()
    requested_fields: tuple[str, ...] = ()

    def __post_init__(self):
        if not str(self.question_id).strip():
            raise ValueError("question_id is required")
        if not str(self.text).strip():
            raise ValueError("question text is required")
        object.__setattr__(self, "source_ids", tuple(int(i) for i in self.source_ids))


@dataclass(frozen=True)
class SourcePassage:
    """Original source text with stable identity and reading scope."""

    source_id: int
    title: str = ""
    identity: Mapping[str, Any] = field(default_factory=dict)
    text: str = ""
    field: str = "body"
    basis: str = "unknown"
    start: int | None = None
    end: int | None = None
    scope_note: str = ""

    def __post_init__(self):
        object.__setattr__(self, "source_id", int(self.source_id))
        if not isinstance(self.text, str):
            raise TypeError("passage text must be a string")


@dataclass(frozen=True)
class VerificationEvidence:
    source_id: int
    quote: str
    field: str = "unknown"
    qualifier: str = ""
    counterevidence: str = ""
    quote_valid: bool = False


@dataclass(frozen=True)
class VerificationAnswer:
    question_id: str
    status: str
    answer: str = ""
    evidence: tuple[VerificationEvidence, ...] = ()
    qualifiers: tuple[str, ...] = ()
    counterevidence: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    parse_warnings: tuple[str, ...] = ()

    @property
    def evidence_status(self) -> str:
        """Whether at least one model-selected quote was located verbatim.

        ``located`` is deliberately weaker than entailment.  It is only a
        guard against treating an invented or mis-copied quote as support.
        """
        if not self.evidence:
            return "none"
        return "located" if any(item.quote_valid for item in self.evidence) else "unlocated"

    @property
    def effective_status(self) -> str:
        """Conservative status for downstream diagnostics.

        A model's ``supported``/``contradicted`` label with no located quote is
        retained in ``status`` but exposed as ``unknown`` here.  Even a located
        quote is not an entailment judgment; downstream code must still assess
        the question-answer relationship independently.
        """
        if self.status == "unknown" or self.evidence_status != "located":
            return "unknown"
        return self.status


@dataclass(frozen=True)
class ClaimPlanningInput:
    """A structured report clause exposed only to a question planner.

    ``text`` is untrusted report wording.  The planner may use it to preserve
    the asserted relationship attributes, but it must not return a verdict or
    a proposed answer.  Source IDs are provenance scope, not evidence.
    """

    claim_id: str
    text: str
    source_ids: tuple[int, ...] = ()
    kind: str = "factual_candidate"
    context: str = ""
    start: int | None = None
    end: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "source_ids", tuple(int(i) for i in self.source_ids))


@dataclass(frozen=True)
class PlannedQuestion:
    question_id: str
    claim_id: str
    text: str
    source_ids: tuple[int, ...] = ()
    requested_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuestionPlanningResult:
    questions: tuple[VerificationQuestion, ...]
    links: tuple[Mapping[str, Any], ...]
    uncovered_claim_ids: tuple[str, ...] = ()
    parse_warnings: tuple[str, ...] = ()
    prompt_sha256: str = ""
    candidate_claim_ids: tuple[str, ...] = ()
    planned_claim_ids: tuple[str, ...] = ()
    budget_limited_claim_ids: tuple[str, ...] = ()


def build_question_planning_prompt(claims: Iterable[ClaimPlanningInput], *, max_claims: int = 12) -> str:
    """Ask a planner for claim-specific neutral questions, without answers.

    The planner sees the exact clause, Markdown role/context, and citation
    scope. It is not given source text, a verdict, or a proposed correction.
    Uncited clauses remain explicit uncovered items instead of being silently
    dropped.
    """
    rows = list(claims)[:max_claims]
    if not rows:
        raise ValueError("at least one claim is required")
    rendered = []
    for claim in rows:
        ids = ", ".join(str(i) for i in claim.source_ids) or "none supplied"
        rendered.append(
            f"CLAIM {claim.claim_id} | role={claim.kind} | source_ids={ids}\n"
            f"context={claim.context or 'none'} | span={claim.start}:{claim.end}\n"
            f"{claim.text}"
        )
    return f"""You are a question planner for an evidence-only verifier.
For each report clause below, create one or two distinct, neutral factual questions that
target the clause's asserted relationship attributes: subject/object,
population or model, intervention/assay/modality, state and direction,
quantities, qualifiers, uncertainty and causal strength. Preserve negation and
scope. Questions must ask what the supplied source establishes; they must not
repeat a proposed answer, issue a verdict, rewrite the claim, or use outside
knowledge. Do not emit a generic "describe the source" question: each question
must target an attribute or relationship that is actually asserted in its
clause. Do not presuppose that any predicate, category, direction, quantity,
or qualifier in the clause is true: phrase the question so the source can
provide the value rather than embedding the clause's label. Every source_id
must come from that claim's listed source_ids. If a
For a mechanism or classification assertion, ask what mechanism or
classification the source reports for the named subject, leaving the value
open; for a direction or quantity assertion, ask what direction or quantity
the source reports. Do not copy a disputed relation label into the question
as a premise. If the model cannot keep the value open, still return the
question for later semantic review rather than inventing a verdict.
claim has no source IDs, still emit a question when its factual assertion can
be queried; use source_ids=[] to mean the bounded original source pack and leave
the lack of an explicit citation visible to reconciliation. Do not invent a
source identity for an uncited clause.

Return JSON only:
{{"plans":[{{"claim_id":"...","questions":[{{"question_id":"...","text":"...",
"source_ids":[1],"requested_fields":["..."]}}]}}]}}
Include every claim_id exactly once, even when its questions list is empty.

REPORT CLAUSES:
{chr(10).join(rendered)}"""


def _parse_question_plans(text: str, claims: tuple[ClaimPlanningInput, ...], *, max_questions: int = 48):
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[1][:-3].strip() if "\n" in value else value[3:-3].strip()
    obj = json.loads(value)
    if not isinstance(obj, dict) or not isinstance(obj.get("plans"), list):
        raise ValueError("planner response must contain plans")
    allowed = {c.claim_id: c for c in claims}
    seen = set(); seen_question_ids = set(); questions = []; links = []; warnings = []
    question_texts = {}
    covered_claims = set()
    for raw in obj["plans"]:
        if not isinstance(raw, dict) or raw.get("claim_id") not in allowed:
            warnings.append("unknown_or_malformed_claim_plan")
            continue
        claim_id = str(raw["claim_id"])
        if claim_id in seen:
            warnings.append(f"duplicate_claim_plan_{claim_id}")
            continue
        seen.add(claim_id)
        claim = allowed[claim_id]
        claim_questions = raw.get("questions") or []
        if not isinstance(claim_questions, list):
            warnings.append(f"malformed_questions_{claim_id}")
            claim_questions = []
        for index, item in enumerate(claim_questions[:2], 1):
            if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                warnings.append(f"malformed_question_{claim_id}")
                continue
            qid = str(item.get("question_id") or f"{claim_id}:q{index}")
            original_qid = qid
            if qid in seen_question_ids:
                # Models often restart q1/q2 for every claim. Scope duplicate
                # IDs deterministically instead of allowing answer parsing to
                # overwrite earlier claims.
                suffix = 2
                scoped = f"{claim_id}:{qid}"
                while scoped in seen_question_ids:
                    scoped = f"{claim_id}:{qid}:{suffix}"
                    suffix += 1
                qid = scoped
                warnings.append(f"duplicate_question_id_scoped_{original_qid}_{claim_id}")
            text_value = " ".join(str(item["text"]).split())
            normalised_text = " ".join(text_value.casefold().split())
            previous_claim = question_texts.get(normalised_text)
            if previous_claim is not None and previous_claim != claim_id:
                # A repeated template does not cover either relationship. Keep
                # both claims visible so a later bounded run can retry them.
                warnings.append(f"duplicate_question_text_{previous_claim}_{claim_id}")
                continue
            raw_ids = item.get("source_ids") or []
            if not isinstance(raw_ids, list):
                warnings.append(f"source_scope_not_list_{qid}")
                continue
            try:
                source_ids = tuple(int(i) for i in raw_ids
                                   if not isinstance(i, bool))
            except (TypeError, ValueError):
                warnings.append(f"invalid_source_scope_{qid}")
                continue
            if claim.source_ids and (not source_ids or not set(source_ids).issubset(set(claim.source_ids))):
                warnings.append(f"source_scope_outside_claim_{qid}")
                continue
            fields = tuple(str(v) for v in (item.get("requested_fields") or []) if v is not None)
            if not fields:
                warnings.append(f"missing_requested_fields_{qid}")
                continue
            questions.append(VerificationQuestion(qid, text_value, source_ids, fields))
            seen_question_ids.add(qid)
            question_texts[normalised_text] = claim_id
            covered_claims.add(claim_id)
            links.append({"question_id": qid, "claim_id": claim_id,
                          "claim_start": claim.start, "claim_end": claim.end,
                          "claim_text_sha256": __import__("hashlib").sha256(claim.text.encode()).hexdigest(),
                          "scope": "cited_sources" if source_ids else "bounded_original_pack",
                          "source_ids_explicit": bool(claim.source_ids),
                          "neutrality_assessment": "unassessed"})
            if len(questions) >= max_questions:
                warnings.append("question_budget_exhausted")
                break
        if len(questions) >= max_questions:
            break
    uncovered = tuple(c.claim_id for c in claims if c.claim_id not in covered_claims)
    return tuple(questions), tuple(links), uncovered, tuple(warnings)


def plan_verification_questions(
    invoke: Callable[[str], Any], claims: Iterable[ClaimPlanningInput], *,
    max_claims: int = 12, max_questions: int = 48,
) -> QuestionPlanningResult:
    """Plan claim-specific neutral questions with strict, bounded decoding."""
    import hashlib
    all_claims = tuple(claims)
    selected = all_claims[:max_claims]
    budget_limited = tuple(c.claim_id for c in all_claims[max_claims:])
    if not selected:
        raise ValueError("at least one claim is required")
    prompt = build_question_planning_prompt(selected, max_claims=max_claims)
    response = invoke(prompt)
    content = response if isinstance(response, str) else getattr(response, "content", response)
    questions, links, uncovered, warnings = _parse_question_plans(str(content), selected,
                                                                    max_questions=max_questions)
    if budget_limited:
        warnings = tuple(warnings) + ("claim_budget_exhausted",)
    all_uncovered = tuple(dict.fromkeys((*uncovered, *budget_limited)))
    planned_claims = tuple(dict.fromkeys(link["claim_id"] for link in links))
    return QuestionPlanningResult(
        questions, links, all_uncovered, warnings,
        hashlib.sha256(prompt.encode()).hexdigest(),
        tuple(c.claim_id for c in all_claims), planned_claims, budget_limited,
    )


def parse_claim_reconciliation_response(
    text: str,
    claim_ids: Iterable[str],
    links: Iterable[Mapping[str, Any]] = (),
) -> tuple[Mapping[str, Any], ...]:
    """Parse the separate claim/answer comparison without dropping gaps."""
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[1][:-3].strip() if "\n" in value else value[3:-3].strip()
    obj = json.loads(value)
    if not isinstance(obj, dict) or not isinstance(obj.get("comparisons"), list):
        raise ValueError("reconciliation response must contain comparisons")
    allowed = tuple(str(v) for v in claim_ids)
    allowed_set = set(allowed)
    linked_questions = {}
    for link in links:
        cid = str(link.get("claim_id") or "")
        qid = str(link.get("question_id") or "")
        if cid in allowed_set and qid:
            linked_questions.setdefault(cid, set()).add(qid)
    rows = {}
    warnings = []
    valid_statuses = {"supported", "partial", "unsupported", "contradicted", "unverifiable", "unknown", "unresolved"}
    for raw in obj["comparisons"]:
        if not isinstance(raw, dict) or str(raw.get("claim_id")) not in allowed_set:
            warnings.append("unknown_reconciliation_claim")
            continue
        claim_id = str(raw["claim_id"])
        if claim_id in rows:
            warnings.append(f"duplicate_reconciliation_claim_{claim_id}")
            continue
        # Current prompts use ``provisional_status``; ``status`` remains a
        # legacy alias. Accept both so a valid comparison is not silently
        # downgraded to unverifiable.
        raw_status = raw.get("status")
        if raw_status is None:
            raw_status = raw.get("provisional_status")
        status_raw = str(raw_status or "unverifiable")
        status = "unverifiable" if status_raw == "unresolved" else status_raw
        if status not in valid_statuses:
            warnings.append(f"invalid_reconciliation_status_{claim_id}")
            status = "unverifiable"
        question_ids = [str(v) for v in (raw.get("question_ids") or [])]
        parse_warnings = []
        expected_questions = linked_questions.get(claim_id, set())
        if expected_questions:
            referenced = expected_questions.intersection(question_ids)
            invalid = sorted(set(question_ids) - expected_questions)
            if not referenced:
                parse_warnings.append("claim_question_coverage_missing")
            elif referenced != expected_questions:
                parse_warnings.append("claim_question_coverage_incomplete")
            if invalid:
                parse_warnings.append("claim_question_id_outside_links")
        rows[claim_id] = {
            "claim_id": claim_id,
            "status": status,
            "status_raw": status_raw,
            "question_ids": question_ids,
            "reason": str(raw.get("reason") or raw.get("notes") or ""),
            "missing_attributes": [str(v) for v in (raw.get("missing_attributes") or [])],
            "qualifier_mismatches": [str(v) for v in (raw.get("qualifier_mismatches") or [])],
            "parse_warnings": parse_warnings,
        }
        if "claim_question_coverage_missing" in parse_warnings:
            rows[claim_id]["status"] = "unverifiable"
    result = []
    for claim_id in allowed:
        if claim_id in rows:
            result.append(rows[claim_id])
        else:
            result.append({"claim_id": claim_id, "status": "unverifiable",
                           "question_ids": [], "reason": "reconciliation omitted this claim",
                           "missing_attributes": [], "qualifier_mismatches": [],
                           "parse_warnings": ["claim_unanswered"]})
    if warnings:
        result.append({"claim_id": "__parser__", "status": "unknown", "question_ids": [],
                       "reason": "reconciliation parser warnings", "missing_attributes": [],
                       "qualifier_mismatches": [], "parse_warnings": warnings})
    return tuple(result)


def summarize_claim_answer_coverage(
    claims: Iterable[ClaimPlanningInput],
    answers: Iterable[VerificationAnswer],
    links: Iterable[Mapping[str, Any]],
) -> Mapping[str, Mapping[str, Any]]:
    """Expose relationship-level coverage before any revision is attempted.

    A non-empty answer list is insufficient when a claim has several planned
    relationships.  This accounting keeps missing questions, unlocated
    quotes, and effective (located but still not entailed) answers distinct so
    callers can preserve incomplete claims instead of revising from one good
    answer.  It is bookkeeping only; ``complete`` does not mean supported.
    """
    claim_rows = tuple(claims)
    answer_map = {str(answer.question_id): answer for answer in answers}
    linked: dict[str, list[str]] = {}
    for link in links:
        claim_id = str(link.get("claim_id") or "")
        question_id = str(link.get("question_id") or "")
        if claim_id and question_id:
            linked.setdefault(claim_id, [])
            if question_id not in linked[claim_id]:
                linked[claim_id].append(question_id)
    coverage: dict[str, Mapping[str, Any]] = {}
    for claim in claim_rows:
        claim_id = str(claim.claim_id)
        expected = list(linked.get(claim_id, []))
        answered = [question_id for question_id in expected if question_id in answer_map]
        located = [question_id for question_id in answered
                   if answer_map[question_id].evidence_status == "located"]
        effective = [question_id for question_id in answered
                     if answer_map[question_id].effective_status != "unknown"]
        missing = [question_id for question_id in expected if question_id not in answer_map]
        unlocated = [question_id for question_id in answered
                     if answer_map[question_id].evidence_status != "located"]
        complete = bool(expected) and set(answered) == set(expected) \
            and set(located) == set(expected) and set(effective) == set(expected)
        if not expected:
            state = "uncovered"
        elif complete:
            state = "complete"
        elif answered:
            state = "partial"
        else:
            state = "unanswered"
        coverage[claim_id] = {
            "claim_id": claim_id,
            "expected_question_ids": expected,
            "answered_question_ids": answered,
            "located_question_ids": located,
            "effective_question_ids": effective,
            "missing_question_ids": missing,
            "unlocated_question_ids": unlocated,
            "complete": complete,
            "state": state,
        }
    return coverage


def reconcile_claim_answers(
    invoke: Callable[[str], Any], claims: Iterable[ClaimPlanningInput],
    answers: Iterable[VerificationAnswer], links: Iterable[Mapping[str, Any]] = (),
) -> tuple[Mapping[str, Any], ...]:
    """Run the explicit comparison stage after source-only answering."""
    claim_rows = tuple(claims)
    prompt = build_claim_reconciliation_prompt(claim_rows, tuple(answers), links)
    response = invoke(prompt)
    content = response if isinstance(response, str) else getattr(response, "content", response)
    rows = parse_claim_reconciliation_response(str(content), (c.claim_id for c in claim_rows), links)
    answer_map = {a.question_id: a for a in answers}
    claim_questions = {}
    for link in links:
        claim_questions.setdefault(str(link.get("claim_id")), []).append(str(link.get("question_id")))
    coverage = summarize_claim_answer_coverage(claim_rows, answers, links)
    guarded = []
    for row in rows:
        claim_id = row.get("claim_id")
        qids = claim_questions.get(claim_id, [])
        mapped = [answer_map[qid] for qid in qids if qid in answer_map]
        claim_coverage = coverage.get(claim_id, {
            "claim_id": claim_id,
            "expected_question_ids": [], "answered_question_ids": [],
            "located_question_ids": [], "effective_question_ids": [],
            "missing_question_ids": [], "unlocated_question_ids": [],
            "complete": False, "state": "uncovered",
        })
        row = dict(row)
        row["coverage"] = claim_coverage
        # A model comparison can be insightful, but a supported/contradicted
        # label is not evidence support when every mapped answer lacks a
        # located quote. Preserve the raw judgment and expose the guard as an
        # unresolved evidence-boundary state for downstream assessment.
        expected_count = len(qids)
        coverage_warnings = set(row.get("parse_warnings") or [])
        if (not claim_coverage["complete"] or not mapped or len(mapped) < expected_count
                or any(answer.effective_status == "unknown" for answer in mapped)
                or {"claim_question_coverage_missing", "claim_question_coverage_incomplete"}.intersection(coverage_warnings)):
            row = dict(row)
            row["status_raw"] = row.get("status_raw", row.get("status"))
            row["status"] = "unverifiable"
            reasons = []
            if not mapped or len(mapped) < expected_count:
                reasons.append("answers_missing")
            if any(answer.effective_status == "unknown" for answer in mapped):
                reasons.append("no_located_quote")
            row["evidence_guard"] = "incomplete_claim_question_coverage"
            row["parse_warnings"] = list(row.get("parse_warnings") or []) + reasons
        guarded.append(row)
    return tuple(guarded)


def build_claim_reconciliation_prompt(
    claims: Iterable[ClaimPlanningInput],
    answers: Iterable[VerificationAnswer],
    links: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Build a separate claim/answer comparison request.

    This request receives the report clause and source-only answer records only
    after verification. It asks for an auditable comparison with unknown and
    partial states; it does not authorize deletion or silently rewrite text.
    """
    claim_rows = {c.claim_id: c for c in claims}
    link_rows = list(links)
    answer_rows = []
    for answer in answers:
        matched = [x for x in link_rows if x.get("question_id") == answer.question_id]
        answer_rows.append({
            "question_id": answer.question_id,
            "claim_ids": [x.get("claim_id") for x in matched],
            "status": answer.status,
            "answer": answer.answer,
            "evidence": [e.__dict__ for e in answer.evidence],
            "qualifiers": list(answer.qualifiers),
            "counterevidence": list(answer.counterevidence),
            "unknowns": list(answer.unknowns),
            "evidence_status": answer.evidence_status,
            "effective_status": answer.effective_status,
            "parse_warnings": list(answer.parse_warnings),
        })
    return f"""Compare each original report clause with the independent source-only
answers below. For each mapped claim, preserve the claim text and source scope,
and report whether the answer covers the asserted subject, relation/direction,
population/model, assay, qualifiers and uncertainty. Use supported, partial,
unsupported, contradicted or unverifiable only as a provisional comparison;
missing or truncated answers remain unresolved. Do not delete, rewrite or
invent claims, and do not treat a located quote as entailment by itself.
Return JSON only with `comparisons` and `uncovered_claim_ids`. Each comparison
must use `provisional_status` (the legacy alias `status` is also accepted) and
put its explanation in `reason` or `notes`.

CLAIMS:
{json.dumps({k: {"text": v.text, "source_ids": v.source_ids, "kind": v.kind,
                  "start": v.start, "end": v.end} for k, v in claim_rows.items()}, ensure_ascii=False)}

INDEPENDENT ANSWERS:
{json.dumps(answer_rows, ensure_ascii=False)}"""


def _source_lines(passages: Iterable[SourcePassage]) -> str:
    """Render only source material; source text remains data, not instructions."""
    rows = []
    for p in passages:
        identity = dict(p.identity or {})
        identity_bits = []
        for key in ("pmid", "doi", "url"):
            value = identity.get(key)
            if value:
                identity_bits.append(f"{key.upper()}={value}")
        identity_text = "; ".join(identity_bits) or "identity unknown"
        scope = p.basis or "scope unknown"
        if p.scope_note:
            scope += f"; {p.scope_note}"
        rows.append(
            f"SOURCE {p.source_id} | {p.title or 'Untitled'} | {identity_text} | "
            f"field={p.field} | basis={scope}\n{p.text}"
        )
    return "\n\n--- SOURCE BOUNDARY ---\n\n".join(rows)


def build_verification_prompt(
    questions: Iterable[VerificationQuestion],
    passages: Iterable[SourcePassage],
) -> str:
    """Build a prompt that cannot anchor the verifier on a draft answer.

    The function intentionally has no ``draft`` or ``verdict`` argument.  The
    only factual input after the neutral questions is the original source text.
    """
    qs = list(questions)
    ps = list(passages)
    if not qs:
        raise ValueError("at least one verification question is required")
    if not ps:
        raise ValueError("at least one original source passage is required")
    question_lines = []
    for q in qs:
        fields = ", ".join(q.requested_fields) if q.requested_fields else "not specified"
        ids = ", ".join(str(i) for i in q.source_ids) if q.source_ids else "all supplied sources"
        question_lines.append(
            f"{q.question_id}: {q.text}\n  requested fields: {fields}\n"
            f"  allowed source IDs for evidence: {ids}"
        )
    return f"""You are an independent evidence reader. Answer the neutral factual questions
using only the original source passages below. Do not use outside knowledge.
Do not infer facts from the question wording. Keep each answer tied to the
source identity and study setting that actually reports it. Preserve negation,
uncertainty, qualifiers, population, assay, platform, quantities and causal
strength. If the supplied passage does not establish an answer, return
unknown and explain the evidence boundary; silence in an abstract is not proof
that the full paper lacks the detail. If sources disagree, report partial or
contradicted with both passages instead of reconciling them silently.

Return JSON only with this shape:
{{"answers": [{{"question_id": "...", "status": "supported|partial|contradicted|unknown",
"answer": "...", "evidence": [{{"source_id": "an integer from that question's source scope", "quote": "exact contiguous quote",
"field": "abstract|methods|results|body", "qualifier": "...",
"counterevidence": "..."}}], "qualifiers": ["..."],
"counterevidence": ["..."], "unknowns": ["..."]}}]}}
Include exactly one answer for every question_id. Evidence quotes must be
contiguous text copied from the supplied passage. Do not assess any report
claim, recommend a rewrite, or remove a source.

NEUTRAL QUESTIONS:
{chr(10).join(question_lines)}

ORIGINAL SOURCE PASSAGES:
{_source_lines(ps)}"""


def _clean_json(text: str) -> Any:
    if not isinstance(text, str):
        raise ValueError("verifier response must be text")
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[1][:-3].strip() if "\n" in value else value[3:-3].strip()
    return json.loads(value)


def parse_verification_response(
    text: str,
    questions: Iterable[VerificationQuestion],
    passages: Iterable[SourcePassage],
) -> tuple[VerificationAnswer, ...]:
    """Parse a response while retaining unresolved and unlocated evidence.

    Invalid source IDs or non-contiguous quotes are not silently discarded:
    they remain on the answer with ``quote_valid=False`` and a warning, making
    a model-selected passage visibly different from verified source support.
    """
    obj = _clean_json(text)
    if not isinstance(obj, dict) or not isinstance(obj.get("answers"), list):
        raise ValueError("verifier response must contain an answers list")
    question_map = {q.question_id: q for q in questions}
    # Keep every supplied passage for an article.  A source can have multiple
    # fields/sections; overwriting earlier passages makes valid quotations
    # appear missing.  IDs are intentionally type-checked below so JSON
    # booleans cannot silently alias article 1 (``int(True) == 1``).
    source_map = {}
    for passage in passages:
        source_map.setdefault(int(passage.source_id), []).append(passage)
    by_id = {}
    for raw in obj["answers"]:
        if not isinstance(raw, dict) or raw.get("question_id") not in question_map:
            continue
        qid = raw["question_id"]
        status = raw.get("status")
        warnings = []
        if status not in ANSWER_STATUSES:
            warnings.append("invalid_or_missing_status")
            status = "unknown"
        evidence_rows = []
        for item in raw.get("evidence") or []:
            if not isinstance(item, dict):
                warnings.append("malformed_evidence_entry")
                continue
            try:
                raw_sid = item.get("source_id")
                if isinstance(raw_sid, bool) or not isinstance(raw_sid, (int, str)):
                    raise ValueError("source ID must be an integer or integer string")
                sid = int(raw_sid)
            except (TypeError, ValueError):
                warnings.append("evidence_source_id_invalid")
                continue
            quote = item.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                warnings.append(f"empty_quote_source_{sid}")
                quote = "" if quote is None else str(quote)
            source = source_map.get(sid, [])
            in_scope = not question_map[qid].source_ids or sid in question_map[qid].source_ids
            valid = bool(source and in_scope and isinstance(quote, str) and quote.strip()
                         and any(quote in passage.text for passage in source))
            if source and not in_scope:
                warnings.append(f"evidence_source_outside_question_scope_{sid}")
            if not valid:
                warnings.append(f"quote_not_located_source_{sid}")
            evidence_rows.append(VerificationEvidence(
                source_id=sid,
                quote=quote,
                field=str(item.get("field") or "unknown"),
                qualifier=str(item.get("qualifier") or ""),
                counterevidence=str(item.get("counterevidence") or ""),
                quote_valid=valid,
            ))
        by_id[qid] = VerificationAnswer(
            question_id=qid,
            status=status,
            answer=str(raw.get("answer") or ""),
            evidence=tuple(evidence_rows),
            qualifiers=tuple(str(v) for v in (raw.get("qualifiers") or []) if v is not None),
            counterevidence=tuple(str(v) for v in (raw.get("counterevidence") or []) if v is not None),
            unknowns=tuple(str(v) for v in (raw.get("unknowns") or []) if v is not None),
            parse_warnings=tuple(warnings),
        )
    answers = []
    for q in question_map.values():
        if q.question_id in by_id:
            answers.append(by_id[q.question_id])
        else:
            answers.append(VerificationAnswer(
                question_id=q.question_id,
                status="unknown",
                unknowns=("verifier omitted this question",),
                parse_warnings=("question_unanswered",),
            ))
    return tuple(answers)


def run_independent_verification(
    invoke: Callable[[str], Any],
    questions: Iterable[VerificationQuestion],
    passages: Iterable[SourcePassage],
) -> tuple[VerificationAnswer, ...]:
    """Run one bounded source-only call; never passes a draft to ``invoke``."""
    qs, ps = tuple(questions), tuple(passages)
    prompt = build_verification_prompt(qs, ps)
    response = invoke(prompt)
    content = response if isinstance(response, str) else getattr(response, "content", response)
    return parse_verification_response(content, qs, ps)
