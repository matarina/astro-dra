"""Offline re-check CLI for requirement 3/4 (cross-verification aid).

Given DOIs/PMIDs, pull the abstract via PubMed ``efetch`` and run the same
:class:`KeywordCoverage` logic the report uses. This lets a reviewer reconcile
the report's hits/misses against an independent fetch.

Usage::

    python -m research_verify.cli_check \
        --pmids 32561899,1234567 \
        --keywords "m6A,hepatocellular carcinoma,METTL3" --threshold 3
"""

from __future__ import annotations

import argparse
import asyncio

from .config import get_config
from .http_client import HttpClient
from .keyword_cov import KeywordCoverage

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def _fetch_abstract(http: HttpClient, pmid: str) -> str:
    res = await http.get(
        EFETCH_URL,
        params={"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "text"},
    )
    return res.text or ""


async def _run(pmids: list[str], keywords: list[str], threshold: int | None) -> int:
    cfg = get_config()
    kc = KeywordCoverage(min_hits=threshold)
    async with HttpClient(cfg) as http:
        texts = await asyncio.gather(*(_fetch_abstract(http, p) for p in pmids))
    rows = []
    for pmid, text in zip(pmids, texts):
        cov = kc.compute({"title": pmid, "full_content": text}, keywords)
        rows.append((pmid, cov))
    print("| PMID | 命中 | 缺失 | 覆盖 | 依据 | 结论 |")
    print("|---|---|---|---|---|---|")
    for pmid, cov in rows:
        verdict = "✅达标" if cov.threshold_ok else "⚠️不达标"
        print(
            f"| {pmid} | {','.join(cov.hits)} | {','.join(cov.missed)} | "
            f"{len(cov.hits)}/{cov.total} | {cov.basis} | {verdict} |"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="research_verify efetch re-check")
    parser.add_argument("--pmids", required=True, help="comma-separated PMIDs")
    parser.add_argument("--keywords", required=True, help="comma-separated")
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args(argv)
    pmids = [p.strip() for p in args.pmids.split(",") if p.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    return asyncio.run(_run(pmids, keywords, args.threshold))


if __name__ == "__main__":
    raise SystemExit(main())
