"""Measure delivery of independently listed references using one parser for both arms."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import mean
from urllib.parse import unquote, urlsplit


def pmid(value):
    value = str(value or "").strip()
    return value if re.fullmatch(r"[1-9][0-9]*", value) else None


def doi(value):
    value = value.strip().casefold() if isinstance(value, str) else ""
    return value if re.fullmatch(r"10\.\d{4,9}/[^\s]+", value) else None


def pmcid(value):
    value = str(value or "").strip().upper()
    return value if re.fullmatch(r"PMC[1-9][0-9]*", value) else None


def matched_identifiers(source, doi_aliases, pmc_aliases):
    values = {pmid(source.get("pmid")), pmid(source.get("_pmid"))}
    dois = {doi(source.get("doi")), doi(source.get("DOI"))}
    pmcs = {pmcid(source.get("pmcid"))}
    try:
        url = urlsplit(str(source.get("link") or source.get("url") or ""))
        host = url.hostname
        path = unquote(url.path).rstrip("/")
        if host in {"pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
            match = re.fullmatch(r"/(?:pubmed/)?([1-9][0-9]*)", path)
            if match:
                values.add(match[1])
        if host in {"europepmc.org", "www.europepmc.org"}:
            match = re.fullmatch(r"/article/MED/([1-9][0-9]*)", path, re.I)
            if match:
                values.add(match[1])
            match = re.fullmatch(r"/article/PMC/(PMC[1-9][0-9]*)", path, re.I)
            if match:
                pmcs.add(match[1].upper())
        if host in {"pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
            match = re.fullmatch(r"/(?:pmc/)?articles/(PMC[1-9][0-9]*)", path, re.I)
            if match:
                pmcs.add(match[1].upper())
        if host in {"doi.org", "dx.doi.org"}:
            dois.add(doi(path.lstrip("/")))
        if host in {"nature.com", "www.nature.com"} and path.startswith("/articles/"):
            dois.add(doi("10.1038/" + path.removeprefix("/articles/").removesuffix(".pdf")))
        if host in {"link.springer.com", "link.springernature.com"} or (host and host.endswith(".biomedcentral.com")):
            match = re.fullmatch(r"/articles?/(10\..+)", path)
            if match:
                dois.add(doi(match[1]))
    except ValueError:
        pass
    for value in dois:
        values.update(doi_aliases.get(value, ()))
    for value in pmcs:
        values.update(pmc_aliases.get(value, ()))
    values.discard(None)
    return values


def backend_status(row, directory):
    failures, upstream = 0, []
    for request in row["requests"]:
        failures += int("error_type" in request or request.get("status_code", 0) >= 400)
        if not request.get("file"):
            continue
        payload = (directory / request["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != request["sha256"]:
            raise ValueError("HTTP response changed")
        try:
            packet = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(packet, dict):
            continue
        unresponsive = packet.get("unresponsive_engines")
        if isinstance(unresponsive, list):
            upstream.extend(unresponsive)
        search = packet.get("esearchresult")
        errors = search.get("errorlist") if isinstance(search, dict) else None
        if isinstance(errors, dict):
            errors = any(errors.values())
        if packet.get("error") or errors:
            failures += 1
    if row["status"] == "raised":
        return "raised", failures, upstream
    if failures or upstream:
        return ("partial" if row.get("returned") else "empty_with_errors"), failures, upstream
    if not row["requests"]:
        return "no_recorded_response", failures, upstream
    return ("returned" if row.get("returned") else "empty"), failures, upstream


def clustered_interval(pairs):
    clusters = defaultdict(list)
    for before, after in pairs:
        if before["known_reference_count"]:
            clusters[before["family"]].append((after["known_hits"] - before["known_hits"],
                                                before["known_reference_count"]))
    totals = [(sum(x for x, _ in rows), sum(y for _, y in rows)) for rows in clusters.values()]
    if len(totals) < 2:
        return None
    rng = random.Random(20261111)
    samples = []
    for _ in range(5000):
        draw = rng.choices(totals, k=len(totals))
        samples.append(sum(x for x, _ in draw) / sum(y for _, y in draw))
    samples.sort()
    return {"families": len(totals), "paired_micro_recall_delta":
            sum(x for x, _ in totals) / sum(y for _, y in totals),
            "percentile_95": [samples[125], samples[4874]]}


def summarize(rows):
    known = [r for r in rows if r["known_reference_count"]]
    clean = [r for r in known if r["backend_status"] in {"returned", "empty"}]
    return {"observations": len(rows), "backend_statuses": dict(Counter(r["backend_status"] for r in rows)),
            "returned_entries": sum(r["returned"] for r in rows),
            "known_hits": sum(r["known_hits"] for r in known),
            "scheduled_known_references": sum(r["known_reference_count"] for r in known),
            "clean_known_hits": sum(r["known_hits"] for r in clean),
            "clean_known_references": sum(r["known_reference_count"] for r in clean),
            "no_reference_pool_observations": len(rows) - len(known),
            "http_requests": sum(r["http_requests"] for r in rows),
            "mean_seconds": mean(r["latency_seconds"] for r in rows) if rows else None}


def collect(root):
    for name, digest in json.loads((root / "freeze.json").read_text())["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen artifact changed: " + name)
    cases = {x["case_id"]: x for x in json.loads((root / "cases.json").read_text())}
    schedule = json.loads((root / "retrieval-schedule.json").read_text())
    gold = {v for case in cases.values() for v in case["known_pool_pmids"]}
    aliases = json.loads((root / "known-reference-epmc-auth.response").read_bytes())
    doi_aliases, pmc_aliases = defaultdict(set), defaultdict(set)
    for row in aliases["resultList"]["result"]:
        if row.get("source") != "MED" or row["id"] not in gold:
            continue
        if doi(row.get("doi")):
            doi_aliases[doi(row["doi"])].add(row["id"])
        if pmcid(row.get("pmcid")):
            pmc_aliases[pmcid(row["pmcid"])].add(row["id"])
    pairs, observations = [], []
    for task in schedule:
        case = cases[task["case_id"]]
        pair = []
        for arm in ("baseline", "candidate"):
            path = root / "retrieval" / arm / (task["engine"] + "-" + case["case_id"] + ".json")
            row = json.loads(path.read_text())
            if row["query"] != case["retrieval_query"] or row["arm"] != arm or row["engine"] != task["engine"]:
                raise ValueError("Mismatched query observation")
            status, failures, upstream = backend_status(row, path.parent)
            known = set(case["known_pool_pmids"])
            located = []
            conflicts = 0
            for rank, source in enumerate(row.get("sources", []), 1):
                identifiers = matched_identifiers(source, doi_aliases, pmc_aliases)
                conflicts += len(identifiers) > 1
                if len(identifiers) == 1 and identifiers <= known:
                    located.append({"rank": rank, "pmid": next(iter(identifiers))})
            result = {k: row[k] for k in ("arm", "engine", "case_id", "family", "variant", "domain", "latency_seconds")}
            result.update(backend_status=status, returned=row.get("returned", 0), http_requests=len(row["requests"]),
                          http_or_provider_failures=failures, upstream_failures=upstream,
                          known_hits=len({h["pmid"] for h in located}), known_reference_count=len(known),
                          located=located, conflicting_identifiers=conflicts,
                          effective_budget=row.get("effective_budget"), started_unix=row["started_unix"])
            pair.append(result)
            observations.append(result)
        pairs.append(pair)
    engine_summaries = {}
    for engine in sorted({x["engine"] for x in observations}):
        arms = {arm: summarize([x for x in observations if x["engine"] == engine and x["arm"] == arm])
                for arm in ("baseline", "candidate")}
        known_pairs = [(b, c) for b, c in pairs if b["engine"] == engine and b["known_reference_count"]]
        clean_pairs = [(b, c) for b, c in known_pairs
                       if b["backend_status"] in {"returned", "empty"} and c["backend_status"] in {"returned", "empty"}]
        engine_summaries[engine] = {"arms": arms, "scheduled_pair_interval": clustered_interval(known_pairs),
                                    "clean_known_pairs": len(clean_pairs),
                                    "clean_pair_interval": clustered_interval(clean_pairs)}
    strata = []
    keys = sorted({(r["engine"], r["arm"], r["domain"], r["variant"]) for r in observations})
    for engine, arm, domain, variant in keys:
        rows = [r for r in observations if (r["engine"], r["arm"], r["domain"], r["variant"]) ==
                (engine, arm, domain, variant)]
        strata.append({"engine": engine, "arm": arm, "domain": domain, "variant": variant, **summarize(rows)})
    return {"scheduled_pairs": len(schedule), "observations": observations, "engine_summaries": engine_summaries,
            "strata": strata, "maximum_pair_dispatch_gap_seconds": max(abs(b["started_unix"]-c["started_unix"]) for b,c in pairs),
            "alias_counts": {"doi": len(doi_aliases), "pmcid": len(pmc_aliases)},
            "relevance_precision": None, "all_literature_recall": None,
            "scope": "Known author-listed PMID delivery only. Unmatched documents and reference-free queries are unjudged. Live preview comparison with sampled family uncertainty."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new results path")
    result = collect(args.root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["engine_summaries"], indent=2))
