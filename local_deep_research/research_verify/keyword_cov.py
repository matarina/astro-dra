"""Requirement 3 -- keyword coverage check (hits over fulltext/abstract).

Given a set of user keywords, count how many appear in a source's full text
(preferred) or abstract+title (fallback), and flag sources under a threshold
(default ``max(min_hits, ceil(ratio*N))`` -- 4 keywords => >=3).

Matching is deliberately simple and explainable: ``str.casefold()`` substring
search, no embeddings. Full-text availability is recorded via ``basis`` so an
abstract-only check is never mistaken for a full-text one.
"""

from __future__ import annotations

import argparse
import json
import math
import re

from loguru import logger

from .config import VerifyConfig, get_config
from .models import KeywordCov
from .textutil import first_nonempty

class KeywordCoverage:
    """Compute keyword coverage for sources."""

    def __init__(
        self,
        cfg: VerifyConfig | None = None,
        model=None,
        min_hits: int | None = None,
        ratio: float | None = None,
    ) -> None:
        self._cfg = cfg or get_config()
        self._model = model
        self._min_hits = min_hits if min_hits is not None else self._cfg.min_keyword_hits
        self._ratio = ratio if ratio is not None else self._cfg.keyword_threshold_ratio

    # -- keyword extraction -------------------------------------------------
    def extract_keywords(self, query: str, settings: dict | None = None) -> list[str]:
        """Only explicit terms have a lexical coverage interpretation.

        The question remains with the writer; no stop-word list or model
        guesses which scientific terms determine relevance.
        """
        raw = (settings or {}).get("keywords")
        if isinstance(raw, str):
            return list(dict.fromkeys(k.strip() for k in re.split(r"[,，;；]", raw) if k.strip()))
        if isinstance(raw, (list, tuple)):
            return list(dict.fromkeys(k.strip() for k in raw if isinstance(k, str) and k.strip()))
        return []

    # -- coverage -----------------------------------------------------------
    def compute(self, source: dict, keywords: list[str]) -> KeywordCov:
        """Compute keyword coverage; never raises."""
        cov = KeywordCov(total=len(keywords), assessment_kind="lexical_overlap", semantic_assessment="not_performed", keyword_provenance="explicit_settings" if keywords else "unknown")
        if not keywords:
            return cov

        text, basis = self._basis_text(source)
        cov.basis = basis
        if not text:
            cov.missed = list(keywords)
            cov.coverage = 0.0
            cov.threshold_ok = False
            return cov

        haystack = text.casefold()
        hits, missed = [], []
        for kw in keywords:
            if kw.casefold() in haystack:
                hits.append(kw)
            else:
                missed.append(kw)
        cov.hits, cov.missed = hits, missed
        cov.coverage = len(hits) / len(keywords)
        cov.threshold_ok = len(hits) >= self._threshold(len(keywords))
        return cov

    def _threshold(self, n: int) -> int:
        return max(int(self._min_hits), math.ceil(self._ratio * n))

    @staticmethod
    def _basis_text(source: dict) -> tuple[str, str]:
        kind = str(source.get("content_type") or "").casefold().replace("-", "_")
        body = first_nonempty(source, ("body",))
        if body:
            return str(body), "fulltext" if kind in {"full_text", "fulltext", "body"} else "body_excerpt"
        full = first_nonempty(source, ("full_content", "content"))
        if full:
            return str(full), "fulltext" if kind in {"full_text", "fulltext"} else "retrieved_text"
        parts = [
            first_nonempty(source, ("abstract",)),
            first_nonempty(source, ("snippet",)),
            first_nonempty(source, ("title", "name")),
        ]
        joined = "\n".join(str(p) for p in parts if p)
        if joined:
            return joined, "abstract"
        return "", "unavailable"


# --------------------------------------------------------------------------- #
# offline re-check CLI (pulls PubMed efetch to cross-verify)
# --------------------------------------------------------------------------- #
def _render(keywords: list[str], results: dict[str, KeywordCov]) -> str:
    lines = ["| 文献 | 命中 | 缺失 | 覆盖 | 依据 | 结论 |", "|---|---|---|---|---|---|"]
    for key, cov in results.items():
        verdict = "✅达标" if cov.threshold_ok else "⚠️不达标"
        lines.append(
            f"| {key} | {','.join(cov.hits)} | {','.join(cov.missed)} | "
            f"{len(cov.hits)}/{cov.total} | {cov.basis} | {verdict} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="research_verify keyword coverage re-check")
    parser.add_argument("--keywords", required=True, help="comma-separated")
    parser.add_argument("--text", help="inline text to check")
    parser.add_argument("--threshold", type=int, default=None)
    args = parser.parse_args(argv)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    kc = KeywordCoverage(min_hits=args.threshold)
    if args.text:
        src = {"title": "inline", "full_content": args.text}
        cov = kc.compute(src, keywords)
        print(_render(keywords, {"inline": cov}))
        print(json.dumps(cov.model_dump(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
