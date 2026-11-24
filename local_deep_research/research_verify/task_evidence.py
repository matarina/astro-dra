"""Targeted evidence retrieval and provenance-bound task coverage."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from .citation_display import cited_indices
from .claims import extract_report_claims
from .generation import ModelOutputTruncated
from .semantic_evidence import merge_passages, semantic_passages
from .source_identity import identity_fields
from .structured_output import object_reply


def gather_evidence(handler, sources, targets, trace, stage, fetcher=None):
    """Read only a bounded list of requested article/question pairs."""
    from .evidence_fetch import EvidenceFetcher

    def read(item):
        source, question = item
        index = int(source["index"])
        url = source.get("_body_url") or source.get("link")
        raw = source.get("fetched_content") or source.get("body")
        receipt = {"source_id": index, "question": question}
        client = fetcher or EvidenceFetcher(handler.settings_snapshot, seconds=16, requests=5)
        pmcid = source.get("_body_pmcid") or identity_fields(source).get("pmcid")
        if not raw:
            before = len(getattr(client, "events", ()))
            try:
                if hasattr(client, "source_article"):
                    article = client.source_article(source)
                else:
                    text = client.article(source)
                    article = {"body": text, "url": url, "status": "retrieved_full_text"} if text else None
            except Exception as exc:
                article = None
                receipt["error_type"] = type(exc).__name__
            attempts = getattr(client, "events", ())[before:]
            receipt["transport_events"] = attempts
            if attempts:
                source.setdefault("_body_attempts", []).extend(attempts)
            if article:
                raw, url = article["body"], article["url"]
                pmcid = article.get("pmcid") or pmcid
                source.update(fetched_content=raw, _body_url=url, _body_acquisition=article["status"],
                              _body_pmcid=pmcid)
        if not raw:
            source["_body_acquisition"] = "full_text_unavailable"
            trace.record(stage, dict(receipt, status="full_text_unavailable"))
            return False
        passages, status = semantic_passages(
            raw, question, lambda prompt: handler._invoke_text(prompt, trace=trace, stage="passage_selection"))
        passages = [dict(passage, url=url) for passage in passages]
        if pmcid and stage == "review_targeted_reread" and hasattr(client, "supplements"):
            from itertools import islice

            try:
                for supplement_url, text in islice(client.supplements(pmcid), 2):
                    supplements, _ = semantic_passages(
                        text, question, lambda prompt: handler._invoke_text(
                            prompt, trace=trace, stage="supplement_passage_selection"))
                    passages.extend(dict(passage, url=supplement_url) for passage in supplements)
            except Exception as error:
                trace.record("supplement_read_unavailable", {
                    "source_id": index, "error_type": type(error).__name__})

        source["_evidence_passages"] = merge_passages(source.get("_evidence_passages", []), passages)
        trace.record(stage, dict(receipt, status=status, passages=passages))
        return bool(passages)

    by_id = {int(source["index"]): source for source in sources}
    questions = {}
    for index, question in targets:
        if index in by_id and identity_fields(by_id[index]):
            questions.setdefault(index, []).append(question)
    items = [(by_id[index], "\n".join(dict.fromkeys(values))) for index, values in questions.items()]
    if not items:
        return False
    with ThreadPoolExecutor(max_workers=1 if fetcher is not None else min(3, len(items))) as pool:
        futures = [pool.submit(copy_context().run, read, item) for item in items]
        results = [future.result() for future in futures]
    return any(results)


def plan_evidence_gaps(handler, plan, sources, draft, trace, fetcher=None):
    questions = [item.get("question") for item in plan.get("questions", []) if item.get("question")]
    if not questions:
        return False
    by_id = {int(source["index"]): source for source in sources}
    cited = cited_indices(draft)
    ranked = list(dict.fromkeys([*cited, *(int(s["index"]) for s in sources if s.get("_screened_task"))]))
    candidates = {index: by_id[index] for index in ranked if index in by_id and identity_fields(by_id[index])}
    if not candidates:
        return False
    per_source = 42_000 // len(candidates)
    previews = []
    for index, source in candidates.items():
        title = (source.get("title") or "")[:min(240, per_source // 3)]
        scope = "original text available" if source.get("fetched_content") or source.get("body") else "abstract only"
        header = f"[{index}] {title} ({scope})"
        preview = source.get("abstract") or source.get("snippet") or ""
        limit = max(0, (per_source - len(header) - 10) // 2)
        if len(preview) > 2 * limit:
            preview = preview[:limit] + " … " + (preview[-limit:] if limit else "")
        previews.append(f"{header}\n{preview}")
    prompt = f"""Identify gaps in evidence for the requested fields/questions.
Pick up to 8 promising papers that need focused rereading of the original study,
and give the missing question(s) for that paper. The prior draft is a lead
only. Missing details in an abstract are not absent from the paper.
Return only JSON {{"gaps": [{{"source_id": 1, "question": "specific missing evidence"}}]}}.
Use only paper source IDs appearing below. Return [] in gaps if no reread is needed.

Task questions: {json.dumps(questions, ensure_ascii=False)}
Prior draft:
{draft[:7000]}

Sources:
""" + "\n\n".join(previews)
    try:
        gaps = object_reply(handler._invoke_text(prompt, trace=trace, stage="task_evidence_gaps")).get("gaps")
    except Exception as error:
        trace.record("task_evidence_gaps_unavailable", {"error_type": type(error).__name__})
        return False
    if not isinstance(gaps, list):
        return False
    targets = [(item["source_id"], item["question"][:900]) for item in gaps[:8]
               if (isinstance(item, dict) and type(item.get("source_id")) is int
                   and item["source_id"] in candidates and isinstance(item.get("question"), str)
                   and item["question"].strip())]
    trace.record("task_evidence_gaps", {"targets": targets})
    return gather_evidence(handler, sources, targets, trace, "task_evidence_reread", fetcher)


OPEN_COVERAGE_STATES = ("partial", "evidence_gap", "missing", "unchecked")
LOCATED_QUOTE_STATES = ("matched", "multiple_matches")


def _question_checks(reply, ids):
    for item in object_reply(reply).get("questions", ()):
        if isinstance(item, dict) and type(item.get("id")) is int and item["id"] in ids:
            yield item


def _check_ids(items, available):
    return [value for value in items if type(value) is int and value in available] if isinstance(items, list) else []


def locate_report_quotes(text, quotes, claims):
    for quote in quotes:
        if not isinstance(quote, str) or not quote.strip():
            yield {"quote": quote, "status": "invalid"}
        elif (start := text.find(quote)) < 0:
            yield {"quote": quote, "status": "not_found"}
        elif text.find(quote, start + 1) >= 0:
            yield {"quote": quote, "status": "multiple_matches", "source_ids": cited_indices(quote)}
        else:
            end = start + len(quote)
            sources = set(cited_indices(quote))
            if not sources:
                for claim in claims:
                    if claim.report_start is not None and claim.report_end is not None and (
                        claim.report_start <= start and end <= claim.report_end
                    ):
                        sources.update(claim.citations)
                if len(sources) > 1:
                    sources.clear()
            yield {"quote": quote, "status": "matched", "start": start, "end": end,
                   "source_ids": sorted(sources)}


def task_coverage(handler, plan, text, trace, *, user_request="", invoke=None):
    """Locate report passages and let the reviewer determine their coverage."""
    questions = [item["question"] for item in plan.get("questions", [])
                 if isinstance(item.get("question"), str) and item["question"].strip()]
    if not questions and not user_request:
        return {}
    invoke = invoke or handler._invoke_text
    context = f"""Original user request:
{user_request}

Research notes (suggested questions): {json.dumps(questions, ensure_ascii=False)}
Report:
{text}
"""
    prompt = f"""Use the original request and report to identify meaningful areas
for coverage review. You may review a combined scope when passages address it
together, or narrow the scope where the available material is limited. Include
substantive requested content that appears unanswered. The research notes
can help locate evidence along with the user's wording.
Copy continuous passages from the report as separate report_quotes. Include
answers, relevant identifying text or citations, and any explicit unknowns.
Use [] where you cannot locate a relevant passage. Return only JSON:
{{"questions": [{{"question": "requested content under review", "status": "partial",
"report_quotes": ["exact report wording"]}}]}}.
Status is answered, partial, evidence_gap or missing.

{context}"""
    claims = extract_report_claims(text)
    passages = {}
    try:
        try:
            reply = object_reply(invoke(prompt, trace=trace, stage="task_coverage"))
        except ModelOutputTruncated:
            # Use IDs instead of asking for a second copy of lengthy report quotes.
            passages = {n: text[c.report_start:c.report_end] for n, c in enumerate(claims, 1)
                        if c.report_start is not None and c.report_end is not None}
            compact = (
                "Identify requested content and whether the report answers it. Include gaps. "
                "For each item return question, status (answered, partial, evidence_gap or missing), "
                "and passage_ids from the numbered report, or [] if unsupported. "
                'JSON only: {"questions":[{"question":"...","status":"partial","passage_ids":[1]}]}.'
                f"\nUser request: {user_request}\nResearch notes: {json.dumps(questions, ensure_ascii=False)}"
                f"\nNumbered passages: {json.dumps(passages, ensure_ascii=False)}"
            )
            trace.record("task_coverage_compact_retry", {"passages": len(passages)})
            reply = object_reply(invoke(compact, trace=trace, stage="task_coverage_compact"))
        proposed = reply.get("questions")
    except Exception as error:
        trace.record("task_coverage_unavailable", {"error_type": type(error).__name__})
        proposed = []
    results = {}
    for item in proposed if isinstance(proposed, list) else ():
        if (not isinstance(item, dict) or not isinstance(item.get("question"), str)
                or not item["question"].strip() or item.get("status") not in ("answered", *OPEN_COVERAGE_STATES)):
            continue
        quotes = item.get("report_quotes")
        if passages:
            ids = item.get("passage_ids")
            quotes = ([passages[i] for i in ids] if isinstance(ids, list)
                      and _check_ids(ids, passages) == ids else [])
        locations = list(locate_report_quotes(text, quotes, claims)) if isinstance(quotes, list) else []
        results[len(results) + 1] = {
            "question": item["question"], "status": "unchecked", "reported_status": item["status"],
            "quote_checks": locations,
            "report_quotes": [row["quote"] for row in locations if row["status"] in LOCATED_QUOTE_STATES],
        }
    if not results:
        results[1] = {"question": user_request or "\n".join(questions), "status": "unchecked",
                      "report_quotes": [], "quote_checks": []}
        trace.record("task_coverage", {"questions": results})
        return results

    located = {
        i: {"question": result["question"], "reported_status": result["reported_status"],
            "passages": {j: row for j, row in enumerate(result["quote_checks"], 1)
                         if row["status"] in LOCATED_QUOTE_STATES}}
        for i, result in results.items()
    }
    instructions = f"""Judge whether the located evidence addresses what the user asked.
Use the original request to interpret the intended scope and the report to
understand context and passage ownership. The located passages establish what
the report says. Describe primary-source verification only if it was performed.
Choose a scope suited to the request. Describe only what you actually checked in
reviewed_scope, and identify what still needs verification in open_scope,
including substantive parts of the request still unaddressed. If the evidence
covers only a sample or part of the requested content, limit the verdict to
that part. Answered means the evidence establishes the requested coverage,
with no remaining gap in that scope. Leave open_scope empty when answered.
Use unchecked if you cannot determine the coverage. Use evidence_gap when the
report only states that its available material cannot establish the answer.
Only explicit evidence from the original can establish that it did not report
something. For evidence you relied on, give the located quote IDs. If sources
are identified in those passages, you may also include their report IDs. A
repeated passage without identifying text may have ambiguous source ownership.
For an open scope, optionally write a concise user_note in the report's
language for the separate review record explaining what this review could and
could not establish. Mention review scope only, without adding source claims.
Return only JSON:
{{"questions":[{{"id":1,"status":"partial","reviewed_scope":"what was checked",
"open_scope":"what remains unverified","quote_ids":[1],"source_ids":[],"user_note":""}}]}}.
Status is answered, partial, evidence_gap, missing or unchecked.

"""
    parts = [located]
    decisions = []
    while parts:
        scope = parts.pop(0)
        prompt = instructions + f"Located passages and questions: {json.dumps(scope, ensure_ascii=False)}\n{context}"
        try:
            decisions.extend(list(_question_checks(invoke(prompt, trace=trace, stage="task_coverage_scope"), scope)))
        except ModelOutputTruncated:
            ids = list(scope)
            trace.record("task_coverage_scope_truncated", {"question_ids": ids})
            if len(ids) > 1:
                middle = len(ids) // 2
                parts[:0] = [{i: scope[i] for i in group} for group in (ids[:middle], ids[middle:])]
        except Exception as error:
            trace.record("task_coverage_scope_unavailable", {"error_type": type(error).__name__})
    for item in decisions:
        index, status = item["id"], item.get("status")
        if status not in ("answered", *OPEN_COVERAGE_STATES):
            continue
        passages = located[index]["passages"]
        proposed_quotes = item.get("quote_ids", [])
        quote_ids = _check_ids(proposed_quotes, passages)
        cited_sources = {source for quote in quote_ids for source in passages[quote]["source_ids"]}
        proposed_sources = item.get("source_ids", [])
        source_ids = _check_ids(proposed_sources, cited_sources)
        reviewed_scope, open_scope = item.get("reviewed_scope"), item.get("open_scope")
        result = results[index]
        result.update(quote_ids=quote_ids, source_ids=source_ids)
        if (quote_ids != proposed_quotes or source_ids != proposed_sources
                or not isinstance(reviewed_scope, str) or not reviewed_scope.strip()
                or (status in ("answered", "partial", "evidence_gap") and not quote_ids)):
            continue
        result["reviewed_scope"] = reviewed_scope.strip()
        if isinstance(open_scope, str) and open_scope.strip():
            result["open_scope"] = open_scope.strip()
            if status == "answered":
                continue
        result["status"] = status
        note = item.get("user_note")
        if (status in ("partial", "evidence_gap", "missing") and isinstance(note, str)
                and note.strip() and set(cited_indices(note)).issubset(cited_sources)):
            result["user_note"] = note.strip()
    trace.record("task_coverage", {"questions": results})
    return results


def plan_coverage_followup(coverage, sources, report, invoke, trace, fetcher, *, user_request=""):
    """Ask the reviewer to choose among the existing evidence retrieval tools."""
    gaps = {i: item for i, item in coverage.items() if item["status"] in OPEN_COVERAGE_STATES}
    if not gaps:
        return []
    by_id = {int(source["index"]): source for source in sources}
    preview_limit = 24_000 // max(1, len(by_id))
    previews = {
        i: {"title": source.get("title"), "url": source.get("link") or source.get("url"),
            "available_text": (source.get("fetched_content") or source.get("body")
                               or source.get("abstract") or source.get("snippet") or "")[:preview_limit],
            "selected_passages": [passage["text"][:preview_limit]
                                  for passage in (source.get("_evidence_passages") or ())[-2:]],
            "reading_status": source.get("_body_acquisition"), "attempts": (source.get("_body_attempts") or ())[-3:]}
        for i, source in by_id.items()
    }
    prompt = f"""Decide whether further evidence can answer these open user questions.
Use the original request, what was checked, remaining gaps, report sources,
located passages, and prior attempts to target the missing material. Return []
if the useful outcome is to state the limits of what is verified. Choose article to reread a known source, or web to retrieve another
primary document. Do not retry the same failed locator without a new reason.
Do not assume material is absent from the original when the available
evidence is incomplete. A source explicitly stating nonreporting can answer
the question within that stated scope. Return only JSON {{"requests": [
{{"question_id": 1, "kind": "article", "source_ids": [1], "query": "focused evidence question"}},
{{"question_id": 2, "kind": "web", "query": "focused primary-document search", "url": "optional known URL"}}]}}.

Original user request: {user_request}
Open questions and evidence: {json.dumps(gaps, ensure_ascii=False)}
Cited source IDs: {cited_indices(report)}
Sources and attempted evidence: {json.dumps(previews, ensure_ascii=False)}
Recent transport attempts: {json.dumps(getattr(fetcher, "events", [])[-8:], ensure_ascii=False)}
Report for context:
{report}
"""
    try:
        requests = object_reply(invoke(prompt, trace=trace, stage="task_coverage_followup")).get("requests")
    except Exception as error:
        trace.record("task_coverage_followup_unavailable", {"error_type": type(error).__name__})
        return []
    issues = []
    for item in requests[:8] if isinstance(requests, list) else ():
        if not isinstance(item, dict) or type(item.get("question_id")) is not int or item["question_id"] not in gaps:
            continue
        kind, query = item.get("kind"), item.get("query")
        if kind not in ("article", "web") or not isinstance(query, str) or not query.strip():
            continue
        source_scope = sorted(set(_check_ids(item.get("source_ids"), by_id)))
        if kind == "article" and not source_scope:
            continue
        request = {"kind": kind, "query": query[:900]}
        if kind == "article":
            request["source_ids"] = source_scope
        elif isinstance(item.get("url"), str):
            request["url"] = item["url"]
        issues.append({"question_id": item["question_id"], "status": "insufficient_evidence", "request": request})
    trace.record("task_coverage_followup", {"requests": issues})
    return issues
