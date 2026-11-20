#!/usr/bin/env python3
"""Run the frozen next-phase arms in an isolated, fixed-source process.

The runner deliberately does not touch the production containers or search
pool.  Each case is synthesized from an immutable source pack with the same
DeepSeek V4 Flash endpoint, output budget, fact-consistency setting and review
budget.  Candidate-specific evidence selection and source-only verification
receipts are stored beside the generated report; they never delete or rewrite
the report automatically.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation/hallucination-next-phase-20261113"
OUT = EVAL / "runs"
ATTEMPT_ID = "unassigned"
RUN_METADATA = {}
ARMS = ("baseline", "semantic_ranking", "evidence_gap", "independent_verification")
OPTIONAL_ARMS = ("identity_attributes",)
SEMANTIC_RANKER_MODE = "llm"
LOCAL_MODEL_PATH = ""
PARAGRAPH_BUNDLES = False
SOURCE_DETAIL_CACHE = None


def _paragraph_bundle_enabled(arm):
    return arm == "evidence_gap" and PARAGRAPH_BUNDLES


def _manifest_cases(path):
    """Explicit original-request inputs; never infer case links by citation ID."""
    payload=json.loads(path.read_text())
    rows=payload.get('cases') if isinstance(payload,dict) else None
    if not isinstance(rows,list) or not rows:raise ValueError('Case manifest needs a nonempty cases list')
    cases=[];seen=set()
    for row in rows:
        case=dict(row);case_id=case.get('case_id');query=case.get('query')
        if not isinstance(case_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',case_id) or case_id in seen:
            raise ValueError('Invalid or duplicate case_id')
        if not isinstance(query,str) or not query.strip():raise ValueError('Missing original query')
        if case.get('query_sha256')!=hashlib.sha256(query.encode()).hexdigest():raise ValueError('Original query hash mismatch')
        for key in ('source','draft'):
            value=case.get(key)
            if key=='draft' and value is None:case[key]=None;continue
            if not isinstance(value,str):raise ValueError('Missing case input path')
            target=Path(value);target=target if target.is_absolute() else ROOT/target
            if not target.is_file():raise ValueError('Case input does not exist: '+str(target))
            if case.get(key+'_sha256')!=sha(target):raise ValueError('Case input hash mismatch: '+key)
            case[key]=target
        seen.add(case_id);cases.append(case)
    return cases


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report_cited_ids(text: str) -> set[int]:
    from research_verify.citation_display import cited_indices
    return set(cited_indices(str(text or "")))


def _revision_claim_audit(before: str, after: str, claim_inputs, coverage):
    """Map textual revision changes back to coverage states.

    This is an assessment receipt, not a scientific gate.  It makes a model
    revision auditable when a broad report is supplied for output formatting:
    incomplete claims remain visible and cannot be mistaken for corrected
    claims merely because another relationship was fully answered.
    """
    from research_verify.claims import extract_report_claims

    normalize = lambda value: " ".join(str(value or "").split())
    before_claims = list(extract_report_claims(str(before or "")))
    after_claims = list(extract_report_claims(str(after or "")))
    after_texts = {normalize(claim.text) for claim in after_claims}
    before_texts = {normalize(claim.text) for claim in before_claims}
    changed = []
    for claim in claim_inputs:
        original = normalize(claim.text)
        if original in after_texts:
            continue
        item = dict(coverage.get(str(claim.claim_id)) or {
            "claim_id": str(claim.claim_id), "state": "uncovered", "complete": False,
        })
        changed.append({
            "claim_id": str(claim.claim_id),
            "original_text": claim.text,
            "coverage_state": item.get("state", "uncovered"),
            "coverage_complete": bool(item.get("complete")),
            "source_ids": list(claim.source_ids),
        })
    added = [
        {"text": claim.text, "report_start": claim.report_start,
         "report_end": claim.report_end}
        for claim in after_claims
        if normalize(claim.text) not in before_texts
    ]
    return {
        "changed_claims": changed,
        "added_claims": added,
        "complete_claim_changes": [item for item in changed if item["coverage_complete"]],
        "incomplete_claim_changes": [item for item in changed if not item["coverage_complete"]],
        "unresolved_for_independent_review": bool(
            any(not item["coverage_complete"] for item in changed) or added
        ),
        "note": "Coverage complete means question/quote bookkeeping only; it is not semantic entailment.",
    }


def _prepare_source_packs() -> dict[str, Path]:
    """Build combined, indexed packs for the two reserved multi-paper tasks."""
    packs = {
        "new-crispr-clinical-safety": ["41810550", "39086133", "39413163"],
        "new-spatial-neuro-oncology": ["42908192", "42677450", "42552377"],
    }
    paths = {}
    target_dir = EVAL / "inputs"
    target_dir.mkdir(parents=True, exist_ok=True)
    for case_id, pmids in packs.items():
        target = target_dir / f"{case_id}.json"
        if not target.exists():
            rows = []
            for index, pmid in enumerate(pmids, 1):
                row = json.loads((EVAL / "sources" / f"pmid-{pmid}.json").read_text())
                row["index"] = str(index)
                row["content"] = row.get("abstract", "")
                row["full_content"] = row.get("abstract", "")
                rows.append(row)
            target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        paths[case_id] = target
    return paths


def _cases(*, source_pack_override=None, draft_override=None) -> list[dict]:
    new = _prepare_source_packs()
    immune_source = Path(source_pack_override) if source_pack_override else (
        ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-immune-base.json"
    )
    immune_draft = Path(draft_override) if draft_override else (
        ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-immune-inherited-draft.md"
    )
    return [
        {
            "case_id": "historical-immune",
            "task_id": "task-47c54edcc0eb",
            "query": "目前关注嗜酸性粒细胞、嗜碱性粒细胞、肥大细胞、T细胞，针对于这些细胞，进行单细胞转录组测序，应该如何进行实验方案，提供文献中是否有能力去对目的细胞进行分选、富集及后续的单细胞实验文章，提取文章中的文选方案，单细胞测序平台，以及如此多的细胞如何分选？",
            "diagnostic_query": "Summarize immune-cell studies and preserve population, methods and findings without merging distinct papers.",
            "source": immune_source,
            "draft": immune_draft,
            "questions": ["population/model for each cited study", "assay/modality and main finding", "qualifiers and unresolved evidence"],
        },
        {
            "case_id": "historical-if",
            "task_id": "task-6ac5d65ed736",
            "query": "调研2026年发表的，影响因子10分以上肿瘤研究的文献，需要提取出20篇文献（按照IF由大到小的顺序）。文献必须同时包含单细胞测序和空间转录组，空转平台可以是10X HD、10X HD3‘、Xenium、Stereo-seq、的其一或者多个，提取出每篇文章的不同组学涉及到分组设计、每组样本数。 注意：1、按照以上要求，只需要对20篇文献的分组设计、每组样本数做信息提取，不要做额外拓展；2、要研究型论文，不能是综述；3、紧密围绕需求做文献调研，不要做额外拓展；4、最终输出的文献只能是按照IF排序的、2026年发表的、20篇研究性论文",
            "diagnostic_query": "Identify 2026 tumor papers containing both single-cell and spatial transcriptomics and report platform/metadata only when supplied.",
            "source": ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-if-base.json",
            "draft": ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-if-inherited-draft.md",
            "questions": ["study identity and publication type", "single-cell and spatial modalities", "platform and IF state", "missing evidence/unknown fields"],
        },
        {
            "case_id": "historical-adipose",
            "task_id": "task-a9b2517baf83",
            "query": "麻烦调研下最近3年的，脂肪样本做的空间转录组的文献，不限平台，影响因子分数越高越好",
            "diagnostic_query": "Survey high-impact adipose spatial-transcriptomics research while distinguishing spatial from non-spatial studies and preserving requested metadata limits.",
            "source": ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-adipose-base.json",
            "draft": ROOT / "evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-adipose-inherited-draft.md",
            "questions": ["which studies actually use spatial transcriptomics", "platform when stated", "study type and journal identity", "important omissions and evidence limitations"],
        },
        {
            "case_id": "new-crispr-clinical-safety",
            "query": "Compare what these sources establish about CRISPR/Cas genome-editing safety, efficacy and translational readiness. Separate clinical-trial evidence, preclinical/IND-enabling evidence and review-level synthesis; identify populations/models, intervention, endpoints, limitations and what remains unknown.",
            "source": new["new-crispr-clinical-safety"],
            "draft": None,
            "questions": ["study type and evidence level per paper", "population/model and intervention", "safety/off-target or efficacy endpoints", "limitations and unresolved risks", "direct findings versus review synthesis"],
        },
        {
            "case_id": "new-spatial-neuro-oncology",
            "query": "Compare how these studies use single-cell and spatial transcriptomics to characterize tumor immunity. Report cohort/model, modalities and platform when supplied, key immune findings, validation, and limits. Do not infer platform, causality or clinical benefit when the abstract does not state it.",
            "source": new["new-spatial-neuro-oncology"],
            "draft": None,
            "questions": ["cohort/model and specimen", "single-cell/spatial modalities and named platform", "immune/TME findings", "validation and outcome evidence", "unknown or abstract-only details"],
        },
    ]


class FrozenEvidence:
    def __init__(self):
        self.events = []

    def record(self, *args, **kwargs):
        return None

    def pmc_identifiers(self, *args, **kwargs):
        return {}

    def article(self, *args, **kwargs):
        self.events.append({"kind": "article", "status": "disabled_fixed_source"})
        return ""

    def web(self, *args, **kwargs):
        self.events.append({"kind": "web", "status": "disabled_fixed_source"})
        return []


class CountingModel:
    def __init__(self, model):
        self.model = model
        self.events = []

    def __getattr__(self, name):
        return getattr(self.model, name)

    def invoke(self, prompt, *args, **kwargs):
        event = {"prompt": str(prompt), "started": time.time()}
        started = time.monotonic()
        try:
            response = self.model.invoke(prompt, *args, **kwargs)
            event.update(status="completed", response=getattr(response, "content", str(response)),
                         metadata=getattr(response, "response_metadata", {}))
            return response
        except BaseException as exc:
            event.update(status="error", error_type=type(exc).__name__)
            raise
        finally:
            event["elapsed_s"] = round(time.monotonic() - started, 3)
            self.events.append(event)


_ARTICLE_EVIDENCE_INIT = None


class CappedRanker:
    """Record ranker calls and keep semantic ranking bounded per report."""

    def __init__(self, model, max_calls: int = 32):
        from research_verify.semantic_reranker import LLMPassageRanker
        self.inner = LLMPassageRanker(model.invoke)
        self.max_calls = max_calls
        self.calls = 0
        self.failures = 0
        self.events = []
        self.selected_batches = []

    def rank(self, query, passages):
        event = {"query_chars": len(str(query)),
                 "passage_count": len(passages),
                 "passage_chars": sum(len(str(p)) for p in passages),
                 "call_index": self.calls + 1}
        if self.calls >= self.max_calls:
            self.failures += 1
            event.update(status="local_failure", error_type="RuntimeError",
                         error="semantic_ranker_budget_exhausted")
            self.events.append(event)
            raise RuntimeError("semantic_ranker_budget_exhausted")
        self.calls += 1
        try:
            # Long question+draft strings exceed the encoder's useful input
            # length. Score bounded sentence/line variants and aggregate by
            # max cosine per passage; this is explicit same-model evidence
            # retrieval, not feedback-driven tuning or entailment.
            variants = [str(query)]
            for part in re.split(r"[\n。！？.!?]+", str(query)):
                part = part.strip()
                if len(part) >= 12 and part not in variants:
                    variants.append(part)
            variants = variants[:12]
            score_rows = [self.inner.rank(variant, passages) for variant in variants]
            scores = [max(row[i] for row in score_rows) for i in range(len(passages))]
            event.update(status="completed", scores=len(scores), query_variants=len(variants))
            self.events.append(event)
            return scores
        except Exception as exc:
            self.failures += 1
            event.update(status="local_failure", error_type=type(exc).__name__,
                         error=str(exc)[:300])
            self.events.append(event)
            raise


class LocalE5Ranker:
    """Evaluation-only local embedding ranker; never changes production settings."""

    def __init__(self, model_path: str):
        from sentence_transformers import SentenceTransformer
        from research_verify.semantic_reranker import SentenceTransformerRanker
        if not model_path:
            raise ValueError("local E5 ranker requires --local-model-path")
        self.model_path = str(model_path)
        self.inner = SentenceTransformerRanker(
            SentenceTransformer(self.model_path, local_files_only=True),
            query_prefix="query: ", passage_prefix="passage: ",
        )
        self.calls = 0
        self.failures = 0
        self.events = []
        self.selected_batches = []

    def rank(self, query, passages):
        event = {"query_chars": len(str(query)),
                 "passage_count": len(passages),
                 "passage_chars": sum(len(str(p)) for p in passages),
                 "call_index": self.calls + 1,
                 "ranker": "local_e5"}
        self.calls += 1
        try:
            scores = self.inner.rank(query, passages)
            event.update(status="completed", scores=len(scores))
            self.events.append(event)
            return scores
        except Exception as exc:
            self.failures += 1
            event.update(status="local_failure", error_type=type(exc).__name__,
                         error=str(exc)[:300])
            self.events.append(event)
            raise


class LocalBGERanker(LocalE5Ranker):
    """Evaluation-only BGE-M3 dense ranker; BGE-M3 needs no query prefix."""

    def __init__(self, model_path: str):
        from sentence_transformers import SentenceTransformer
        from research_verify.semantic_reranker import SentenceTransformerRanker
        if not model_path:
            raise ValueError("local BGE-M3 ranker requires --local-model-path")
        self.model_path = str(model_path)
        self.inner = SentenceTransformerRanker(
            SentenceTransformer(self.model_path, local_files_only=True),
            query_prefix="", passage_prefix="",
        )
        self.calls = 0
        self.failures = 0
        self.events = []
        self.selected_batches = []


def _neutral_questions(case, report="", sources=()):
    from research_verify.independent_verification import (
        ClaimPlanningInput, plan_verification_questions,
    )
    from research_verify.claims import extract_report_claims
    available = {int(s.get("index")) for s in sources if str(s.get("index", "")).isdigit()}
    claims = []
    for claim_index, claim in enumerate(extract_report_claims(str(report)), 1):
        source_ids = tuple(i for i in claim.citations if i in available)
        claims.append(ClaimPlanningInput(
            claim_id=f"claim-{claim_index}", text=claim.text,
            source_ids=source_ids, kind=claim.kind, context=claim.context,
            start=claim.report_start, end=claim.report_end,
        ))
    # The semantic planner sees the exact clause and its structured source
    # scope, then emits neutral attribute questions. It is separate from the
    # source-only answerer and has no access to evidence or verdicts.
    return claims, plan_verification_questions


def _passages(sources):
    from research_verify.independent_verification import SourcePassage
    from research_verify.generation import source_material
    out = []
    for source in sources:
        # Reuse the canonical source-material selector so acquired body text
        # (including fetched_content) reaches the verifier.  The old adapter
        # preferred abstract and silently discarded fetched material.
        text, basis = source_material(source)
        if not text:
            continue
        fields = []
        for field in ("abstract", "full_content", "content", "body", "fetched_content", "snippet"):
            value = source.get(field)
            if isinstance(value, str) and value.strip() and value in text:
                fields.append(field)
        field = "+".join(fields) or "source_material"
        scope = f"canonical source_material fields={field}; {basis}"
        out.append(SourcePassage(
            int(source["index"]), source.get("title", ""),
            {k: source.get(k) for k in ("pmid", "doi", "link") if source.get(k)},
            text, field=field, basis="fixed source snapshot",
            start=0, end=len(text), scope_note=scope,
        ))
    return tuple(out)


def _bound_passages(passages, max_chars=60000):
    """Keep bounded original text while recording every scope decision.

    An oversized passage is clipped at the explicit budget boundary and marked
    truncated; it is never both kept and labelled omitted. Later sources remain
    in the omission ledger instead of disappearing when the first source fills
    the budget.
    """
    from dataclasses import replace
    kept, used, omissions = [], 0, []
    for passage in passages:
        size = len(passage.text)
        remaining = max_chars - used
        if remaining <= 0:
            omissions.append({"source_id": passage.source_id, "status": "omitted_budget",
                              "original_chars": size, "kept_chars": 0})
            continue
        if size > remaining:
            clipped = replace(
                passage,
                text=passage.text[:remaining],
                end=(passage.start or 0) + remaining,
                scope_note=(passage.scope_note + "; " if passage.scope_note else "")
                + f"truncated by verifier budget {max_chars} chars",
            )
            kept.append(clipped)
            used += remaining
            omissions.append({"source_id": passage.source_id, "status": "truncated_budget",
                              "original_chars": size, "kept_chars": remaining})
            continue
        kept.append(passage)
        used += size
    return tuple(kept), tuple(omissions)


def _gap_receipt(case, sources, *, context_budget=40000, draft="", paragraph_bundles=False):
    if paragraph_bundles:
        from research_verify.generation import source_material
        from research_verify.paragraph_bundle_candidate import build_request_bundle_context
        documents = [SimpleNamespace(page_content=source_material(source)[0],
                                     metadata={"index": source["index"]}) for source in sources]
        context, _plan, planning = build_request_bundle_context(
            documents, str(case.get("query") or ""), context_chars=max(0, int(context_budget)))
        return {"status": "active_writer_context", "writer_context": context,
                "paragraph_bundle_planning": planning,
                "writer_context_sha256": hashlib.sha256(
                    json.dumps(context, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                "influences_writer_input": bool(context),
                "follow_up_acquisition": "disabled_fixed_source"}
    from research_verify.passages import retrieve_gap_passages
    from research_verify.evidence_selection import select_request_field_windows, select_context_windows
    from research_verify.evidence_cards import build_passage_card
    from research_verify.coverage_planner import CoverageCandidate, plan_coverage
    from research_verify.citation_display import cited_indices
    priority_source_ids = {int(i) for i in cited_indices(str(draft or ""))}
    rows = retrieve_gap_passages(
        "", case["questions"], source_id=None,
        follow_up=lambda _q: None,
        window_chars=1400, max_passages=2,
    )
    # Also run against each supplied source. This records candidate windows
    # without claiming that any window entails the requested fact. The field
    # vocabulary is neutral navigation metadata, not a topic filter or a
    # feedback label; the original case questions remain explicit variants.
    field_queries = {
        "study_population": (
            "population model specimen cell type sample quantity",
            "study population or experimental model",
        ),
        "sorting_enrichment": (
            "method protocol cell sorting enrichment isolation gating antibodies",
            "cell separation or enrichment procedure",
        ),
        "assay_platform": (
            "assay modality single-cell sequencing platform transcriptome flow cytometry",
            "experimental assay and named platform",
        ),
        "outcome_limits": (
            "reported finding outcome validation limitation uncertainty",
            "result and evidence limitation",
        ),
    }
    for index, question in enumerate(case.get("questions") or (), 1):
        field_queries[f"case_question_{index}"] = (str(question),)
    by_source = []
    source_records = []
    planned_cards = []
    for source in sources:
        from research_verify.generation import source_material
        text, basis = source_material(source)
        if not text:
            continue
        source_records.append({
            "source_id": source["index"],
            "title": str(source.get("title") or ""),
            "text": text,
            "basis": f"fixed_source_snapshot; canonical source_material; {basis}",
            "identity": {key: source.get(key) for key in
                         ("doi", "pmid", "pmcid", "link", "title")},
        })
        selected = select_request_field_windows(
            text, field_queries, source_id=source["index"],
            window_chars=2000, max_windows_per_field=4,
            context_chars=min(12000, max(1600, len(text))),
            adjacent_windows=True,
        )
        # Keep the legacy question-directed rows in the receipt for comparison;
        # only the field-planned cards are sent to the writer candidate arm.
        legacy = retrieve_gap_passages(
            text, case["questions"], source_id=source["index"],
            basis=f"fixed_source_snapshot; canonical source_material; {basis}",
            window_chars=1400, max_passages=2,
        )
        by_source.extend(legacy)
        for row in selected:
            for card in row.passage_cards:
                by_source.append({
                    "question": row.field,
                    "source_id": row.source_id,
                    "basis": f"fixed_source_snapshot; canonical source_material; {basis}",
                    "status": row.status,
                    "window": card,
                })
                planned_cards.append({
                    "source_id": row.source_id,
                    "field": row.field,
                    "card": card,
                    "basis": f"fixed_source_snapshot; canonical source_material; {basis}",
                    "priority": int(row.source_id) in priority_source_ids,
                })
        if (int(source["index"]) in priority_source_ids
                and not any(int(item["source_id"]) == int(source["index"])
                            for item in planned_cards)):
            fallback_windows = select_context_windows(
                text, " ".join(map(str, case.get("questions") or ())),
                window_chars=1600, max_windows=1, overlap_chars=200,
            )
            for window in fallback_windows[:1]:
                card = build_passage_card(
                    source["index"], text, window.start, window.end, window.text,
                    field="priority_source", method=window.method,
                    score=window.score, lexical_match=window.lexical_match,
                )
                by_source.append({
                    "question": "priority_source", "source_id": source["index"],
                    "basis": f"fixed_source_snapshot; canonical source_material; {basis}",
                    "status": "candidate_passages", "window": card,
                })
                planned_cards.append({
                    "source_id": source["index"], "field": "priority_source",
                    "card": card,
                    "basis": f"fixed_source_snapshot; canonical source_material; {basis}",
                    "priority": True,
                })

    # First reserve a bounded complete-text lane for long acquired sources.
    # This is an opt-in source-scoped reading path: the writer receives
    # original bytes, never a generated summary, and the lane carries no
    # support verdict.
    full_text_budget = max(0, int(context_budget))
    query_terms = set()
    query_terms.update(str(case.get("query") or "").casefold().split())
    for values in field_queries.values():
        for value in values:
            query_terms.update(str(value).casefold().split())
    full_candidates = []
    for item in source_records:
        if len(item["text"]) < 10000:
            continue
        lexical_hint = sum(
            1 for token in query_terms
            if token and token in (item["title"] + " " + item["text"]).casefold()
        )
        full_candidates.append((lexical_hint, item))
    full_context = []
    full_used = 0
    from research_verify.evidence_cards import build_complete_source_card
    for _hint, item in sorted(
        full_candidates, key=lambda row: (-row[0], str(row[1]["source_id"]))
    ):
        size = len(item["text"])
        if full_used + size > full_text_budget:
            continue
        card = build_complete_source_card(
            item["source_id"], item["text"], basis=item["basis"],
            source_identity=item.get("identity"),
        )
        full_context.append({
            "source_id": item["source_id"],
            "question": "complete_source_text",
            "text": card["text"],
            "start": card["offsets"]["start"],
            "end": card["offsets"]["end"],
            "method": card["method"],
            "lexical_match": card["lexical_match"],
            "basis": card["scope"],
            "field": card["field"],
            "text_sha256": card["text_sha256"],
            "source_text_sha256": card["source_text_sha256"],
            "source_identity": card.get("source_identity", {}),
            "completeness": card["completeness"],
        })
        full_used += size

    # Apply one deterministic global budget after per-source field coverage.
    # This prevents a large source pool from turning the opt-in candidate arm
    # into an unbounded prompt while retaining field/source diversity.
    candidates = [CoverageCandidate(
        source_id=item["source_id"],
        start=item["card"]["offsets"]["start"],
        end=item["card"]["offsets"]["end"],
        text=item["card"]["text"],
        fields=(item["field"],),
        score=(float(item["card"].get("relevance_hint") or 0.0)
               + (1000.0 if item.get("priority") else 0.0)),
        method=item["card"].get("method", "candidate"),
        lexical_match=bool(item["card"].get("lexical_match", False)),
    ) for item in planned_cards]
    required_fields = list(dict.fromkeys(item["field"] for item in planned_cards))
    plan = plan_coverage(
        candidates, required_fields,
        context_chars=max(0, full_text_budget - full_used),
        min_sources=min(12, len({str(item.source_id) for item in candidates})),
    )
    chosen = {item.key for item in plan.selected}
    context = list(full_context)
    for item in planned_cards:
        card = item["card"]
        key = (str(item["source_id"]), card["offsets"]["start"], card["offsets"]["end"])
        if key not in chosen:
            continue
        context.append({
            "source_id": item["source_id"],
            "question": item["field"],
            "text": card["text"],
            "start": card["offsets"]["start"],
            "end": card["offsets"]["end"],
            "method": card.get("method", "coverage_planner"),
            "lexical_match": card.get("lexical_match", False),
            "basis": item["basis"],
            "field": card.get("field", item["field"]),
            "text_sha256": card.get("text_sha256"),
            "source_text_sha256": card.get("source_text_sha256"),
        })
    return {
        "status": "active_writer_context",
        "missing_material_probe": [r.__dict__ for r in rows],
        "source_selections": [
            {"question": r.question, "source_id": r.source_id, "basis": r.basis,
             "status": r.status,
             "windows": [w.__dict__ for w in r.windows]}
            for r in by_source if not isinstance(r, dict)
        ] + [
            {"question": r.get("question", ""), "source_id": r.get("source_id"),
             "basis": r.get("basis", ""), "status": r.get("status", "candidate_passages"),
             "field": (r.get("window") or {}).get("field"),
             "windows": [r.get("window") or {}]}
            for r in by_source if isinstance(r, dict)
        ],
        "follow_up_acquisition": "disabled_fixed_source",
        "writer_context": context,
        "writer_context_sha256": hashlib.sha256(
            json.dumps(context, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "influences_writer_input": bool(context),
        "complete_source_context": {
            "budget_chars": full_text_budget,
            "selected_source_ids": [item["source_id"] for item in full_context],
            "selected_chars": full_used,
            "candidate_count": len(full_candidates),
            "note": "verbatim acquired text; completeness of published paper remains unconfirmed",
        },
        "coverage_plan": {
            "required_fields": plan.required_fields,
            "covered_fields": plan.covered_fields,
            "uncovered_fields": plan.uncovered_fields,
            "source_ids": plan.source_ids,
            "context_chars": full_used + plan.context_chars,
            "context_sha256": plan.context_sha256,
            "candidate_count": len(candidates),
            "selected_count": len(plan.selected),
            "note": "candidate availability only; no support or entailment verdict",
            "priority_source_ids": sorted(priority_source_ids),
        },
    }


def run_case(case, arm, fixed_report=None):
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handler import CitationHandler
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy, SearchResultsCollector
    from research_verify.synthesis_trace import trace_context
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    from research_verify.independent_verification import run_independent_verification
    from research_verify import source_evidence

    out = OUT / case["case_id"] / arm
    out.mkdir(parents=True, exist_ok=True)
    source_path = case["source"]
    source_payload = json.loads(source_path.read_text())
    # Supervisor source packets are recorded as {"sources": [...]}; older
    # frozen packs are plain lists. Preserve the packet envelope/hash while
    # passing only the unannotated source records to the research flow.
    sources = source_payload.get("sources", source_payload) if isinstance(source_payload, dict) else source_payload
    if not isinstance(sources, list):
        raise TypeError("source pack must contain a list of source records")
    draft = case["draft"].read_text() if case["draft"] and case["draft"].exists() else ""
    defaults = Path(__import__("local_deep_research").__file__).parent / "defaults/default_settings.json"
    snap = apply_environment_overrides_to_snapshot({k: v.get("value") for k, v in json.loads(defaults.read_text()).items()})
    snap.update({
        "llm.provider": "openai_endpoint", "llm.model": "deepseek-v4-flash", "llm.temperature": 0,
        "llm.max_tokens": 5000, "llm.request_timeout": 600, "llm.max_retries": 1,
        "general.enable_fact_checking": True, "citation.enable_source_reading": True,
        "citation.enable_source_reading_roles": False,
        "citation.semantic_passage_ranking": arm == "semantic_ranking",
        # Matched bounded writer-input budget makes the selection candidate
        # reachable on the historical multi-paper packs; the full source
        # snapshots remain preserved on disk and are never deleted.
        "citation.source_context_chars": 60000,
        "citation.evidence_gap_context_chars": 20000 if arm == "evidence_gap" else 0,
        "citation.paragraph_bundle_coverage": _paragraph_bundle_enabled(arm),
        "citation.source_detail_material": arm == "evidence_gap" and SOURCE_DETAIL_CACHE is not None,
        "citation.identity_attribute_review": arm == "identity_attributes",
        "citation.max_review_calls": 6,
        "citation.empty_response_retry_max_tokens": 10000,
        "search.tool": "pubmed", "search.iterations": 1, "search.questions_per_iteration": 1,
    })
    if arm == "semantic_ranking" and SEMANTIC_RANKER_MODE in {"local_e5", "local_bge_m3"}:
        # Feedback-blind query expansion: original draft wording is only a
        # retrieval hint and never a support or correction verdict.
        snap["citation.claim_directed_source_context"] = True
    row = {
        "schema_version": "hallucination_next_phase_run.v2", "attempt_id": ATTEMPT_ID,
        "case_id": case["case_id"], "task_id": case.get("task_id"), "arm": arm,
        "source_pack": str(source_path),
        "source_pack_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_count": len(sources),
        "draft_path": str(case["draft"]) if case.get("draft") else None,
        "draft_sha256": (hashlib.sha256(case["draft"].read_bytes()).hexdigest()
                          if case.get("draft") and case["draft"].exists() else None),
        "fixed_report_path": str(fixed_report) if fixed_report else None,
        "fixed_report_sha256": (hashlib.sha256(fixed_report.read_bytes()).hexdigest()
                                 if fixed_report and fixed_report.exists() else None),
        "model": "deepseek-v4-flash", "query": case["query"],
        "diagnostic_query": case.get("diagnostic_query"),
        "query_sha256": hashlib.sha256(case["query"].encode()).hexdigest(),
        "diagnostic_query_sha256": hashlib.sha256(str(case.get("diagnostic_query", "")).encode()).hexdigest(),
        "source_file": str(source_path),
        "source_sha256": sha(source_path), "source_count": len(sources),
        "settings": {k: snap.get(k) for k in ("llm.model", "llm.temperature", "llm.max_tokens",
                      "general.enable_fact_checking", "citation.semantic_passage_ranking", "citation.max_review_calls",
                      "citation.source_context_chars", "citation.paragraph_bundle_coverage",
                      "citation.source_detail_material", "citation.identity_attribute_review")},
        "protocol": {"version": "v2-60000", "source_context_chars": 60000,
                     "image": RUN_METADATA.get("image"), "image_id": RUN_METADATA.get("image_id"),
                     "code_sha256": RUN_METADATA.get("code_sha256"),
                     "case_manifest_sha256": RUN_METADATA.get("case_manifest_sha256"),
                     "semantic_ranker_mode": SEMANTIC_RANKER_MODE,
                     "local_model_path": LOCAL_MODEL_PATH if SEMANTIC_RANKER_MODE == "local_e5" else None},
        "draft_chars": len(draft), "status": "running", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate": {"evidence_gap": arm == "evidence_gap", "semantic_ranking": arm == "semantic_ranking",
                      "identity_attributes": arm == "identity_attributes",
                      "independent_verification": arm == "independent_verification"},
    }
    global _ARTICLE_EVIDENCE_INIT
    if _ARTICLE_EVIDENCE_INIT is None:
        _ARTICLE_EVIDENCE_INIT = source_evidence.ArticleEvidenceClient.__init__
    original_init = _ARTICLE_EVIDENCE_INIT
    def frozen_init(self, *args, **kwargs):
        kwargs["fetcher"] = FrozenEvidence()
        original_init(self, *args, **kwargs)
    source_evidence.ArticleEvidenceClient.__init__ = frozen_init
    model = None
    started = time.monotonic()
    try:
        with settings_context(SimpleNamespace(username=None, get_setting=lambda k, d=None: snap.get(k, d))):
            model = CountingModel(get_llm(settings_snapshot=snap))
            strategy = LangGraphAgentStrategy.__new__(LangGraphAgentStrategy)
            strategy.model = model; strategy.settings_snapshot = snap
            strategy.get_setting = lambda k, d=None: snap.get(k, d)
            strategy.collector = SearchResultsCollector(); strategy.collector._results = copy.deepcopy(sources)
            strategy.collector._sources = [s.get("link", "") for s in sources]
            strategy.all_links_of_system = []; strategy._update_progress = lambda *a, **k: None
            strategy._build_egress_context = lambda: None; strategy._format_citations = lambda body, records: body
            strategy.citation_handler = CitationHandler(model, handler_type="standard", settings_snapshot=snap)
            handler = getattr(strategy.citation_handler, "_handler", strategy.citation_handler)
            handler.evidence_fetcher = FrozenEvidence()
            if arm == "semantic_ranking":
                # The historical pilot used eight and exhausted locally. Keep
                # that receipt immutable; future attempts use the declared
                # bounded budget and record every call/failure event.
                handler.semantic_passage_ranker = (
                    LocalBGERanker(LOCAL_MODEL_PATH)
                    if SEMANTIC_RANKER_MODE == "local_bge_m3"
                    else LocalE5Ranker(LOCAL_MODEL_PATH)
                    if SEMANTIC_RANKER_MODE == "local_e5"
                    else CappedRanker(model, max_calls=32)
                )
            gap_receipt = None
            if arm == "evidence_gap":
                # Run question-directed retrieval before writing, then expose
                # only labelled candidate windows through the opt-in handler
                # hook. Selection is not an entailment or deletion decision.
                if SOURCE_DETAIL_CACHE is not None:
                    handler.source_detail_reader_receipts = [json.loads(p.read_text())
                        for p in sorted(SOURCE_DETAIL_CACHE.glob('source-*.json'))]
                    gap_receipt = {"status": "source_detail_cache", "writer_context": [],
                                   "cache_sha256": RUN_METADATA.get("source_detail_cache_sha256")}
                else:
                    gap_receipt = _gap_receipt(
                        case, sources,
                        context_budget=int(snap.get('citation.evidence_gap_context_chars', 0)),
                        draft=draft,
                        paragraph_bundles=bool(snap.get("citation.paragraph_bundle_coverage", False)),
                    )
                handler.evidence_gap_context = gap_receipt.get("writer_context", [])
            if fixed_report:
                # A fixed-body replay isolates the post-write diagnostic from
                # writer sampling. The verifier remains advisory and the
                # original body is preserved alongside any revision.
                result = {"current_knowledge": fixed_report.read_text(),
                          "search_results": copy.deepcopy(sources),
                          "fixed_report_replay": True}
            else:
                with trace_context(f"hallucination-next-{case['case_id']}-{arm}"):
                    result = strategy._finalize(case["query"], draft, 0, 0, [])
            body = result.get("current_knowledge") or ""
            if not body.strip():
                raise RuntimeError("empty_report")
            publication = publish_report(body, result.get("search_results", sources), cfg=VerifyConfig(enable_citation_qc=False))
            row.update(status="completed", body=body, report_sha256=hashlib.sha256(body.encode()).hexdigest(),
                       references=len(publication.sources), report_chars=len(body), publication=publication.metadata(),
                       research_result={k: result.get(k) for k in ("error", "iterations")}, model_calls=len(model.events))
            # Persist the generated report before optional candidate
            # diagnostics.  A verifier parse failure must not erase a valid
            # report or turn the entire arm into an unrecorded failure.
            (out / "report.md").write_text(body)
            if arm == "evidence_gap":
                row["evidence_gap"] = gap_receipt
                # Persist the final writer-material receipt produced by
                # evidence_flow. This is the post-append attachment state,
                # not merely the pre-write candidate planning receipt.
                row["candidate_attachment_receipts"] = getattr(
                    handler, "writer_context_receipts", [])
            if arm == "identity_attributes":
                row["candidate_attachment_receipts"] = getattr(handler,"writer_context_receipts",[])
            if arm == "independent_verification":
                from research_verify.independent_verification import (
                    reconcile_claim_answers, summarize_claim_answer_coverage,
                )
                claim_inputs, planner = _neutral_questions(case, body, sources)
                planning_error = None
                try:
                    planning = planner(model.invoke, claim_inputs, max_claims=12, max_questions=24)
                    questions = list(planning.questions)
                    question_links = list(planning.links)
                    question_basis = "semantic_claim_planner"
                    planning_meta = {
                        "prompt_sha256": planning.prompt_sha256,
                        "uncovered_claim_ids": list(planning.uncovered_claim_ids),
                        "parse_warnings": list(planning.parse_warnings),
                        "claim_count": len(claim_inputs),
                        "candidate_claim_ids": list(planning.candidate_claim_ids),
                        "planned_claim_ids": list(planning.planned_claim_ids),
                        "budget_limited_claim_ids": list(planning.budget_limited_claim_ids),
                    }
                except Exception as exc:
                    questions, question_links = [], []
                    question_basis = "planner_failed"
                    planning_error = {"error_type": type(exc).__name__, "error": str(exc)[:500]}
                    planning_meta = {"claim_count": len(claim_inputs), "uncovered_claim_ids": [c.claim_id for c in claim_inputs]}
                passages = _passages(sources)
                # Batch source-scoped questions so a single long verifier
                # response cannot erase all answers when it stops at length.
                batches = [questions[i:i + 2] for i in range(0, len(questions), 2)]
                answers, failures = [], []
                scope_omissions = []
                if planning_error:
                    failures.append({"stage": "question_planning", **planning_error})
                for batch in batches:
                    scoped_ids = {sid for q in batch for sid in q.source_ids}
                    candidate_passages = (tuple(p for p in passages if p.source_id in scoped_ids)
                                          if scoped_ids else passages)
                    scoped_passages, bound_records = _bound_passages(candidate_passages, 60000)
                    scope_omissions.append({"question_ids": [q.question_id for q in batch],
                                            "source_scope": sorted(scoped_ids),
                                            "bound_records": list(bound_records),
                                            "omitted_source_ids": [r["source_id"] for r in bound_records
                                                                    if r["status"] == "omitted_budget"],
                                            "truncated_source_ids": [r["source_id"] for r in bound_records
                                                                      if r["status"] == "truncated_budget"],
                                            "passage_chars": sum(len(p.text) for p in scoped_passages)})
                    try:
                        answers.extend(run_independent_verification(model.invoke, batch, scoped_passages))
                    except Exception as exc:
                        failures.append({"question_ids": [q.question_id for q in batch],
                                         "source_ids": sorted(scoped_ids),
                                         "error_type": type(exc).__name__, "error": str(exc)[:500]})
                answer_rows = [a.__dict__ | {
                    "evidence_status": a.evidence_status, "effective_status": a.effective_status,
                    "evidence": [e.__dict__ for e in a.evidence],
                } for a in answers]
                claim_answer_coverage = summarize_claim_answer_coverage(
                    claim_inputs, answers, question_links,
                )
                reconciliation_rows = []
                if answers and question_links:
                    try:
                        reconciliation_rows = reconcile_claim_answers(
                            model.invoke, claim_inputs, answers, question_links)
                    except Exception as exc:
                        failures.append({"stage": "reconciliation", "error_type": type(exc).__name__,
                                         "error": str(exc)[:500]})
                complete_claim_ids = {
                    claim_id for claim_id, item in claim_answer_coverage.items()
                    if item.get("complete")
                }
                complete_question_ids = {
                    question_id
                    for claim_id, item in claim_answer_coverage.items()
                    if claim_id in complete_claim_ids
                    for question_id in item.get("expected_question_ids", [])
                }
                # A located answer may still belong to an incomplete claim.
                # Only fully covered claim relationships may influence the
                # optional revision; every other answer remains diagnostic.
                usable_answers = [a for a in answers
                                  if a.question_id in complete_question_ids
                                  and a.effective_status != "unknown"]
                complete_claim_rows = [
                    {"claim_id": claim.claim_id, "text": claim.text,
                     "source_ids": list(claim.source_ids),
                     "coverage": claim_answer_coverage.get(str(claim.claim_id), {})}
                    for claim in claim_inputs if str(claim.claim_id) in complete_claim_ids
                ]
                complete_answer_rows = [
                    row for row in answer_rows if row.get("question_id") in complete_question_ids
                ]
                complete_reconciliation_rows = [
                    row for row in reconciliation_rows
                    if str(row.get("claim_id")) in complete_claim_ids
                ]
                diagnostic_notes = {
                    "answers": answer_rows,
                    "claim_answer_coverage": claim_answer_coverage,
                    "reconciliation": list(reconciliation_rows),
                    "failures": failures,
                }
                revision_notes = {
                    "target_claims": complete_claim_rows,
                    "answers": complete_answer_rows,
                    "reconciliation": complete_reconciliation_rows,
                    "note": "Only complete question/quote coverage is supplied here; complete is bookkeeping, not entailment.",
                }
                notes = json.dumps(revision_notes, ensure_ascii=False, indent=2)
                revision_prompt = f"""Revise the report using the original report and the independent
source-only reading notes below. Preserve useful supported coverage and source
identities. Correct a statement only when a quoted source passage or an
explicit unknown/qualifier warrants it. Keep uncertainty, counterevidence and
abstract-only limits visible. Do not invent evidence, citations, or verdicts;
this is a comparison/revision step, not an automatic deletion gate.
Only the claim IDs in TARGET CLAIMS may be changed. Copy every other report
span verbatim, including claims with incomplete, missing, unlocated or
uncovered evidence. Coverage completion is bookkeeping, not semantic
entailment.

ORIGINAL REPORT:
{body}

INDEPENDENT SOURCE-ONLY READING NOTES:
{notes}

Return the revised report text only, retaining valid citation indices."""
                revision_input_sha = hashlib.sha256(revision_prompt.encode()).hexdigest()
                revised = ""
                revision_performed = bool(usable_answers)
                if revision_performed:
                    try:
                        revision_response = model.invoke(revision_prompt)
                        revised = str(getattr(revision_response, "content", revision_response) or "").strip()
                    except Exception as exc:
                        failures.append({"stage": "revision", "error_type": type(exc).__name__,
                                         "error": str(exc)[:500]})
                else:
                    failures.append({"stage": "revision", "error_type": "NoUsableVerificationAnswers",
                                     "error": "original report preserved; no non-unknown source-scoped answers"})
                changed = bool(revised and revised != body)
                revision_claim_audit = _revision_claim_audit(
                    body, revised, claim_inputs, claim_answer_coverage,
                ) if changed else {
                    "changed_claims": [], "added_claims": [],
                    "complete_claim_changes": [], "incomplete_claim_changes": [],
                    "unresolved_for_independent_review": False,
                    "note": "No revised body was produced; coverage is bookkeeping only.",
                }
                if changed:
                    (out / "report-before-revision.md").write_text(body)
                    (out / "report.md").write_text(revised)
                    row["body"] = revised
                    row["report_sha256"] = hashlib.sha256(revised.encode()).hexdigest()
                    row["report_chars"] = len(revised)
                    # Publication metadata must describe the final revised
                    # body, while the pre-revision body remains preserved.
                    revised_publication = publish_report(
                        revised, result.get("search_results", sources),
                        cfg=VerifyConfig(enable_citation_qc=False),
                    )
                    row["publication"] = revised_publication.metadata()
                    row["references"] = len(revised_publication.sources)
                row["independent_verification"] = {
                    "status": "completed" if answers and not planning_error else "unavailable",
                    "draft_excluded": True, "question_count": len(questions),
                    "batch_count": len(batches), "answers": answer_rows,
                    "diagnostic_notes": diagnostic_notes,
                    "reconciliation": list(reconciliation_rows),
                    "failures": failures,
                    "source_scoped": True,
                    "question_basis": question_basis,
                    "planning": planning_meta,
                    "claim_answer_coverage": claim_answer_coverage,
                    "question_links": question_links,
                    "scope_omissions": scope_omissions,
                    "verified_source_ids": sorted({sid for q in questions for sid in q.source_ids}),
                    "unverified_cited_source_ids": sorted(_report_cited_ids(body) -
                                                            {sid for q in questions for sid in q.source_ids}),
                    "revision": {"performed": revision_performed, "changed": changed,
                                 "input_sha256": revision_input_sha,
                                 "influences_downstream_report": changed,
                                 "usable_answer_count": len(usable_answers),
                                 "complete_claim_ids": sorted(complete_claim_ids),
                                 "incomplete_claim_ids": sorted(
                                     claim_id for claim_id, item in claim_answer_coverage.items()
                                     if not item.get("complete")),
                                 "revision_input_claim_ids": sorted(complete_claim_ids),
                                 "claim_audit": revision_claim_audit,
                                 "gain_assessment": "unresolved_pending_independent_review"
                                 if revision_claim_audit.get("unresolved_for_independent_review")
                                 else "not_assessed",},
                }
            if arm == "semantic_ranking":
                ranker = getattr(handler, "semantic_passage_ranker", None)
                row["semantic_ranking"] = {
                    "status": "active_writer_selection",
                    "ranker_mode": SEMANTIC_RANKER_MODE,
                    "injected": ranker is not None,
                    "calls": getattr(ranker, "calls", 0),
                    "failures": getattr(ranker, "failures", 0),
                    "max_calls": getattr(ranker, "max_calls", None),
                    # Preserve the local failure boundary and every bounded
                    # rank invocation.  Aggregate counts alone cannot tell
                    # prompt-budget failures from malformed model output.
                    "ranker_events": getattr(ranker, "events", []),
                    "call_events": getattr(ranker, "events", []),
                    "selected_batches": getattr(ranker, "selected_batches", []),
                    "selection_receipts": (result.get("evidence_review", {}) or {}).get(
                        "semantic_selection_receipts",
                        getattr(handler, "semantic_selection_receipts", []),
                    ),
                    "writer_context_receipts": (result.get("evidence_review", {}) or {}).get(
                        "writer_context_receipts",
                        getattr(handler, "writer_context_receipts", []),
                    ),
                    "writer_selection_reached": getattr(ranker, "calls", 0) > 0,
                    "note": "rank scores are selection metadata, not support or entailment verdicts",
                }
            # The report was written before diagnostics; preserve it even when
            # a candidate-side diagnostic is unavailable.
    except BaseException as exc:
        row.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:1000],
                   model_calls=len(model.events) if model else 0)
    finally:
        source_evidence.ArticleEvidenceClient.__init__ = original_init
        row["elapsed_s"] = round(time.monotonic() - started, 3)
        row["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if model is not None:
            (out / "calls.json").write_text(json.dumps(model.events, ensure_ascii=False, indent=2, default=str))
            row["model_calls"] = len(model.events)
        (out / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({k: row.get(k) for k in ("case_id", "arm", "status", "report_chars", "elapsed_s", "model_calls", "error_type")}, ensure_ascii=False), flush=True)
    return row


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="all")
    ap.add_argument("--case-manifest", default=None, help="Explicit hash-frozen case inputs; bypass built-in cases")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--attempt-id", default=None,
                    help="Immutable output directory name; reruns must use a new value")
    ap.add_argument("--image", default=os.environ.get("DRA_EVAL_IMAGE", "unknown"))
    ap.add_argument("--image-id", default=os.environ.get("DRA_EVAL_IMAGE_ID", "unknown"))
    ap.add_argument("--source-pack", default=None,
                    help="Override the historical-immune fixed source pack")
    ap.add_argument("--draft", default=None,
                    help="Override the historical-immune inherited/original draft")
    ap.add_argument("--fixed-report", default=None,
                    help="Replay a frozen report body and skip writer generation")
    ap.add_argument("--semantic-ranker", choices=("llm", "local_e5", "local_bge_m3"), default="llm")
    ap.add_argument("--local-model-path", default="")
    ap.add_argument("--paragraph-bundles", action="store_true",
                    help="Enable request-only paragraph bundles in evidence_gap only; default off")
    ap.add_argument("--source-detail-cache", default=None, help="Candidate-only canonical reader cache; default off")
    args = ap.parse_args()
    global OUT, ATTEMPT_ID, RUN_METADATA, SEMANTIC_RANKER_MODE, LOCAL_MODEL_PATH, PARAGRAPH_BUNDLES, SOURCE_DETAIL_CACHE
    ATTEMPT_ID = args.attempt_id or time.strftime("attempt-%Y%m%dT%H%M%SZ", time.gmtime())
    SEMANTIC_RANKER_MODE = args.semantic_ranker
    LOCAL_MODEL_PATH = args.local_model_path
    PARAGRAPH_BUNDLES = args.paragraph_bundles
    SOURCE_DETAIL_CACHE = Path(args.source_detail_cache).resolve() if args.source_detail_cache else None
    if SOURCE_DETAIL_CACHE is not None and PARAGRAPH_BUNDLES:
        raise SystemExit("Choose either source-detail-cache or paragraph-bundles")
    if "/" in ATTEMPT_ID or ATTEMPT_ID in {"", ".", ".."}:
        raise SystemExit("invalid attempt id")
    OUT = EVAL / "runs" / ATTEMPT_ID
    if OUT.exists() and any(OUT.iterdir()) and not args.force:
        raise SystemExit(f"immutable attempt directory already contains files: {OUT}")
    RUN_METADATA = {
        "image": args.image,
        "image_id": args.image_id,
        "code_sha256": {name: sha(ROOT / name) for name in (
            "scripts/run_hallucination_next_phase_experiment_20261113.py",
            "local_deep_research/research_verify/evidence_flow.py",
            "local_deep_research/research_verify/independent_verification.py",
            "local_deep_research/research_verify/evidence_selection.py",
            "local_deep_research/research_verify/coverage_planner.py",
            "local_deep_research/research_verify/paragraph_bundle_candidate.py",
            "local_deep_research/research_verify/generation.py",
            "local_deep_research/research_verify/source_detail_material.py",
            "local_deep_research/research_verify/source_reader_candidate.py",
            "local_deep_research/overlay/base_citation_handler.py",
        )},
    }
    if SOURCE_DETAIL_CACHE is not None:
        RUN_METADATA["source_detail_cache_sha256"] = {p.name: sha(p) for p in sorted(SOURCE_DETAIL_CACHE.glob("source-*.json"))}
        if not RUN_METADATA["source_detail_cache_sha256"]:
            raise SystemExit("Empty source-detail-cache")
    source_override = Path(args.source_pack).resolve() if args.source_pack else None
    draft_override = Path(args.draft).resolve() if args.draft else None
    fixed_report = Path(args.fixed_report).resolve() if args.fixed_report else None
    if args.case_manifest:
        if source_override or draft_override:raise SystemExit('Use case-manifest or source/draft overrides')
        manifest_path=Path(args.case_manifest).resolve()
        RUN_METADATA['case_manifest_sha256']=sha(manifest_path)
        cases=_manifest_cases(manifest_path)
    else:cases = _cases(source_pack_override=source_override, draft_override=draft_override)
    if args.cases != "all":
        wanted = set(args.cases.split(",")); cases = [c for c in cases if c["case_id"] in wanted]
    arms = [a for a in args.arms.split(",") if a in ARMS+OPTIONAL_ARMS]
    if fixed_report and 'identity_attributes' in arms:
        raise SystemExit('identity_attributes requires actual synthesis/native checking; fixed-report replay bypasses it')
    rows = []
    for case in cases:
        for arm in arms:
            target = OUT / case["case_id"] / arm / "result.json"
            if target.exists() and not args.force:
                rows.append(json.loads(target.read_text())); continue
            rows.append(run_case(case, arm, fixed_report=fixed_report))
    selected_case = next((case for case in cases if case["case_id"] == "historical-immune"), None)
    selected_payload = (json.loads(selected_case["source"].read_text())
                        if selected_case and selected_case["source"].exists() else None)
    selected_sources = (selected_payload.get("sources", selected_payload)
                        if isinstance(selected_payload, dict) else selected_payload)
    receipt = {"schema_version": "hallucination_next_phase_results.v2", "attempt_id": ATTEMPT_ID,
               "protocol": {"version": "v4-fixed-writer-replay" if fixed_report else "v3-matched-original-immune", "source_context_chars": 60000,
                            "image": args.image, "image_id": args.image_id,
                            "source_pack": str(selected_case["source"]) if selected_case else None,
                            "source_pack_sha256": (sha(selected_case["source"])
                                                   if selected_case and selected_case["source"].exists() else None),
                            "source_count": len(selected_sources) if isinstance(selected_sources, list) else None,
                            "draft": str(selected_case["draft"]) if selected_case else None,
                            "fixed_report": str(fixed_report) if fixed_report else None,
                            "fixed_report_sha256": (sha(fixed_report)
                                                     if fixed_report and fixed_report.exists() else None),
                            "original_query_sha256": hashlib.sha256(selected_case["query"].encode()).hexdigest()
                            if selected_case else None,
                            "code_sha256": RUN_METADATA["code_sha256"],
                            "case_manifest_sha256": RUN_METADATA.get("case_manifest_sha256")},
               "arms": arms,
               "cases": [c["case_id"] for c in cases], "rows": rows,
               "production_deployed": False, "source_pool_live": False,
               "model": "deepseek-v4-flash", "temperature": 0, "max_output_tokens": 5000,
               "semantic_ranker_mode": SEMANTIC_RANKER_MODE,
               "local_model_path": LOCAL_MODEL_PATH if SEMANTIC_RANKER_MODE == "local_e5" else None}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "completed": sum(r.get("status") == "completed" for r in rows),
                      "failed": sum(r.get("status") not in {"completed", "skipped"} for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
