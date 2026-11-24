"""A single source-scoped eligibility ledger for a constrained research task."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import json

from .jcr_adapter import passes_threshold
from .structured_output import object_reply
from .textutil import first_year


def has_eligibility_constraints(plan):
    return bool(plan.get("eligibility") or plan.get("publication_years")
                or plan.get("report_publication_years"))


def assess_eligibility(handler, plan, documents, sources, trace, candidate_ids, *, journal_selection=None):
    from .generation import _source_blocks

    # A single sentence can establish several independent requirements.
    criteria = {i: entry["criterion"] for i, entry in enumerate(plan.get("eligibility", []), 1)
                if isinstance(entry.get("criterion"), str) and entry["criterion"].strip()}
    years = plan.get("report_publication_years") or plan.get("publication_years")
    selection = journal_selection or {}
    ledger, reviewable = {}, set()
    for source in sources:
        index = int(source["index"])
        if index not in candidate_ids:
            continue
        status, reasons = "pending", []
        receipt = (source.get("_jcr_check") or {}) if selection else {}
        metric = (receipt.get("impact_factor") if receipt.get("status") == "found"
                  and receipt.get("requested_metric_year") == selection["year"] else None)
        year = first_year(source)
        if years and year is not None and not years["start"] <= year <= years["end"]:
            reasons.append("outside_requested_publication_years")
            status = "excluded"
        if passes_threshold(metric, selection.get("minimum"), selection.get("operator", ">=")) is False:
            reasons.append("below_confirmed_impact_threshold")
            status = "excluded"
        if years and year is None:
            reasons.append("publication_year_unverified")
        if selection and metric is None:
            reasons.append("impact_factor_unverified")
        ledger[index] = {"status": status, "reasons": reasons, "criteria": {},
                         "publication_year": year, "impact_factor": metric}
        if status != "excluded":
            reviewable.add(index)
    if not criteria and (years or selection):
        for index in reviewable:
            if not ledger[index]["reasons"]:
                ledger[index]["status"] = "confirmed"
    if not reviewable or not criteria:
        trace.record("task_eligibility", {"sources": ledger})
        return ledger
    batches, batch, chars = [], {}, 0
    for index, block in _source_blocks(documents, ""):
        if index not in reviewable:
            continue
        if batch and chars + len(block) > 45_000:
            batches.append(batch)
            batch, chars = {}, 0
        batch[index] = block
        chars += len(block)
    if batch:
        batches.append(batch)

    def check(batch):
        prompt = f"""Check explicit inclusion criteria, independently, using only the same
paper's metadata and original passages. For each source ID and criterion ID,
return supported, contradicted or unknown. Use one to three short, exact and
continuous original spans. Put separately located evidence in separate items.
For a joint criterion, quote evidence for each required method or condition.
Keep the study context. Never combine two nonadjacent spans into one quotation.
Authors citing another study does not verify use in this study. Leave unknown
if absence from a supplied excerpt is the only evidence. Additional requested
report fields should be checked later and do not determine eligibility.
Return only JSON {{"checks": [{{"source_id": 1, "criterion_id": 1,
"status": "supported", "quotes": ["first exact span", "second exact span"]}}]}}.

Criteria: {json.dumps(criteria, ensure_ascii=False)}

Sources:
""" + "\n\n".join(batch.values())
        try:
            response = object_reply(handler._invoke_text(prompt, trace=trace, stage="task_eligibility"))
        except Exception as exc:
            trace.record("task_eligibility_unavailable", {"sources": list(batch), "error_type": type(exc).__name__})
            return {}
        checked = {}
        checks = response.get("checks")
        if not isinstance(checks, list):
            trace.record("task_eligibility_unavailable", {"sources": list(batch), "error_type": "checks_not_list"})
            return {}
        for item in checks:
            if not isinstance(item, dict):
                continue
            index, criterion = item.get("source_id"), item.get("criterion_id")
            status = item.get("status")
            quotes = item.get("quotes", [item.get("quote")])
            if type(index) is not int or index not in batch or type(criterion) is not int or criterion not in criteria:
                continue
            if status not in ("supported", "contradicted") or not isinstance(quotes, list) or not 1 <= len(quotes) <= 3:
                continue
            locations = [{"quote": quote, "source_block_start": start} for quote in quotes
                         if isinstance(quote, str) and quote.strip() and (start := batch[index].find(quote)) >= 0]
            if len(locations) != len(quotes):
                continue
            result = {"status": status, **locations[0]}
            if len(locations) > 1:
                result["additional_evidence"] = locations[1:]
            entries = checked.setdefault(index, {})
            if criterion in entries and entries[criterion]["status"] != status:
                entries[criterion] = {"status": "unknown"}
            else:
                entries[criterion] = result
        return checked

    if batches:
        with ThreadPoolExecutor(max_workers=min(3, len(batches))) as pool:
            futures = [pool.submit(copy_context().run, check, batch) for batch in batches]
            for future in futures:
                for index, checks in future.result().items():
                    item = ledger[index]
                    item["criteria"] = checks
                    if any(c["status"] == "contradicted" for c in checks.values()):
                        item["status"] = "excluded"
                    elif not item["reasons"] and set(checks) == set(criteria) and all(
                        c["status"] == "supported" for c in checks.values()
                    ):
                        item["status"] = "confirmed"
    trace.record("task_eligibility", {"sources": ledger})
    return ledger


def eligibility_lists(ledger, sources, *, metric_order=None):
    confirmed, pending = [], []
    for source in sources:
        index = int(source["index"])
        if index not in ledger:
            continue
        status = ledger[index]["status"]
        if status == "confirmed":
            confirmed.append(index)
        elif status == "pending":
            pending.append(index)
    if metric_order:
        direction = 1 if metric_order == "ascending" else -1
        confirmed.sort(key=lambda index: direction * ledger[index]["impact_factor"])
    return confirmed, pending


def missing_supporting_quotes(ledger, confirmed, views):
    """Supply original assertions lost when a writer view was compacted."""
    receipts = {}
    for index in confirmed:
        present = views.get(index, {}).get("block", "")
        for assessment in ledger[index]["criteria"].values():
            if assessment["status"] != "supported":
                continue
            for evidence in [assessment, *assessment.get("additional_evidence", [])]:
                quote = evidence.get("quote")
                if quote and quote not in present:
                    receipts[index, quote] = {"source_id": index, "quote": quote,
                                              "source_block_start": evidence["source_block_start"]}
    return list(receipts.values())


def carry_eligibility_quotes(material, quotes):
    """Keep validated originals in the actual source-scoped prompt view."""
    from .generation import SourceMaterial
    from .synthesis_trace import text_digest

    grouped = {}
    for row in quotes:
        grouped.setdefault(row["source_id"], []).append(row)
    rendered = str(material)
    views = dict(material.views)
    for index, rows in grouped.items():
        view = views[index]
        addition = "\n\n" + "\n\n".join(
            f"ORIGINAL PASSAGE (admission evidence, expanded source offset {row['source_block_start']}):\n{row['quote']}"
            for row in rows
        )
        text = view["text"] + addition
        original_block = view["block"]
        block = original_block.replace(f"BEGIN SOURCE TEXT\n{view['text']}\nEND SOURCE TEXT",
                                       f"BEGIN SOURCE TEXT\n{text}\nEND SOURCE TEXT", 1)
        rendered = rendered.replace(original_block, block, 1)
        views[index] = {**view, "text": text, "block": block, "model_view_chars": len(text),
                        "model_view_sha256": text_digest(text), "admission_evidence": rows}
    return SourceMaterial(rendered, views)
