"""Explicitly enabled, request-only paragraph bundles for evidence-gap writing.

No model, acquisition, feedback, evaluator annotations or draft citations enter
this module. Relevance hints and structural coverage never establish support.
"""
from __future__ import annotations

import hashlib
import re

from .coverage_planner import (
    generate_paragraph_bundles, index_source_structure,
    paragraph_bundle_delivery_receipts, plan_paragraph_bundles,
)


SETTING = 'citation.paragraph_bundle_coverage'


def build_request_bundle_context(documents, request: str, *, context_chars: int):
    """Index all paragraphs first; select bounded lexical seeds per local section.

    Fields are exact nonblank request lines, not domain labels or caller-provided
    case questions. Zero-match field/source pairs remain explicitly unseeded.
    Unicode word overlap is only a transparent relevance hint, with no dictionary.
    """
    fields = tuple(dict.fromkeys(part.strip() for line in request.splitlines() for part in re.split(r'[，。；：！？!?\n]+', line) if part.strip()))
    sources = tuple(index_source_structure(str(d.page_content or ''),
                                          source_id=d.metadata['index']) for d in documents)
    candidates, opportunities = [], []
    for source in sources:
        seeds = {}
        for field in fields:
            terms = set(re.findall(r'[^\W_]+', field.casefold()))
            sections = {}
            for index, paragraph in enumerate(source.paragraphs):
                value = ' '.join(paragraph.heading_path) + ' ' + source.text[paragraph.start:paragraph.end]
                hint = len(terms & set(re.findall(r'[^\W_]+', value.casefold())))
                if hint:
                    sections.setdefault(paragraph.section_id, []).append((hint, index))
            chosen = []
            for options in sections.values():
                for _hint, index in sorted(options, key=lambda row: (-row[0], row[1]))[:2]:
                    seeds.setdefault(index, []).append(field)
                    chosen.append(index)
            if not chosen:
                # Cross-language/unknown-token fallback: structural navigation only.
                # It preserves explicit uncertainty and never treats layout as support.
                first_by_section = {}
                for index, paragraph in enumerate(source.paragraphs):
                    first_by_section.setdefault(paragraph.section_id, index)
                for index in sorted(first_by_section.values())[:2]:
                    seeds.setdefault(index, []).append(field)
                    chosen.append(index)
                seed_state = 'structural_seed_fallback' if chosen else 'unseeded_unknown'
            else:
                seed_state = 'seeded'
            opportunities.append(dict(source_id=source.source_id, source_sha256=source.sha256,
                                      field=field, paragraph_count=len(source.paragraphs),
                                      seed_paragraphs=sorted(chosen),
                                      state=seed_state))
        candidates.extend(generate_paragraph_bundles(source, seeds))
    plan = plan_paragraph_bundles(candidates, context_chars=context_chars, canonical_sources=sources)
    context = [dict(source_id=b.source.source_id, start=b.start, end=b.end,
                    text=b.text, field='\n'.join(b.fields), fields=list(b.fields),
                    text_sha256=hashlib.sha256(b.text.encode()).hexdigest(),
                    source_text_sha256=b.source.sha256, method='paragraph_bundle',
                    basis='request_only; canonical acquired source; structural bundle')
               for b in plan.selected]
    receipt = dict(schema_version='paragraph_bundle_planning.v1', enabled=True,
                   request_sha256=hashlib.sha256(request.encode()).hexdigest(),
                   fields=[dict(text=f, sha256=hashlib.sha256(f.encode()).hexdigest()) for f in fields],
                   canonical_sources=[dict(source_id=s.source_id, sha256=s.sha256) for s in sources],
                   opportunities=opportunities, candidate_count=len(candidates),
                   selected_count=len(plan.selected), budget_chars=plan.budget_chars,
                   serialized_chars=plan.context_chars, context_sha256=plan.context_sha256,
                   planning_receipts=list(plan.receipts),
                   seed_rule='whole-source index; positive Unicode word overlap; up to two seeds per field/local section',
                   note='candidate relevance and acquired structure only; no support or entailment')
    return context, plan, receipt


def prepare_bundle_candidate(handler, request, documents, gap_context, *, context_chars):
    """Both an evidence-gap hook and an explicit setting are required."""
    if gap_context is None or not bool(handler.get_setting(SETTING, False)):
        return gap_context, None, None
    return build_request_bundle_context(documents, request, context_chars=context_chars)


def bundle_writer_receipt(plan, planning, material, source_ids, candidate_receipts):
    """Map hardened formatter proofs to canonical bundle/material coordinates.

    Only unchanged source-block proofs for matching source/offset/hash/field cards
    establish bound spans. Bare source prose, registry IDs and legacy/unbound
    fallback rows never establish attachment.
    """
    final_text = str(material)
    spans = []
    for bundle in plan.selected:
        field = '\n'.join(bundle.fields)
        for receipt in candidate_receipts:
            for card in receipt.get('cards', ()):
                if (card.get('status') not in {'attached', 'attached_text_registry_absent'}
                        or card.get('source_id') != bundle.source.source_id
                        or card.get('source_text_sha256') != bundle.source.sha256
                        or card.get('offsets') != {'start': bundle.start, 'end': bundle.end}
                        or card.get('text_sha256') != hashlib.sha256(bundle.text.encode()).hexdigest()
                        or card.get('field') != field):
                    continue
                proof = card.get('delivery_binding') or {}
                if (proof.get('source_id') != bundle.source.source_id
                        or proof.get('source_text_sha256') != bundle.source.sha256
                        or not card.get('canonical_binding_sha256')
                        or proof.get('canonical_binding_sha256') != card['canonical_binding_sha256']):
                    continue
                a, b = proof.get('material_start'), proof.get('material_end')
                if not (type(a) is int and type(b) is int and 0 <= a < b <= len(final_text)):
                    continue
                block = final_text[a:b]
                prefix = f'Field: {field}\nCandidate passage (supplementary; not an entailment verdict):\n'
                row = prefix + bundle.text
                if (hashlib.sha256(block.encode()).hexdigest() != proof.get('source_block_sha256')
                        or hashlib.sha256(row.encode()).hexdigest() != proof.get('candidate_row_sha256')
                        or row not in block):
                    continue
                start = a + block.rindex(row) + len(prefix)
                spans.append(dict(source_id=bundle.source.source_id, source_sha256=bundle.source.sha256,
                                  source_start=bundle.start, source_end=bundle.end,
                                  material_start=start, material_end=start + len(bundle.text)))
    canonical = tuple({b.source.source_id: b.source for b in plan.selected}.values())
    delivery = paragraph_bundle_delivery_receipts(
        plan, final_text, delivered_spans=spans, final_source_registry=source_ids,
        canonical_sources=canonical)
    return dict(schema_version='paragraph_bundle_writer_context.v1', planning=planning,
                delivery_receipts=list(delivery),
                final_material_chars=len(final_text),
                final_material_sha256=hashlib.sha256(final_text.encode()).hexdigest(),
                final_registry_ids=sorted(source_ids),
                note='formatting exposure only; partial means bound prose without exact helper wire card')


def persist_bundle_writer_receipt(writer_context_receipts, plan, planning, material,
                                  source_ids, candidate_receipts, trace, batch):
    """Persist only when enabled; use the writer's final material and registry."""
    if plan is None:
        return
    receipt = bundle_writer_receipt(plan, planning, material, source_ids, candidate_receipts)
    writer_context_receipts[-1]['paragraph_bundle_receipts'] = receipt
    trace.record('paragraph_bundle_writer_context', {'batch': batch, **receipt})
