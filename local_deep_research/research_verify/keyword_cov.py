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

_ZH_STOP = set("的了吗呢和在是有与及等为对以")
_EN_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "study", "research", "analysis", "review",
}


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
        """Return keywords from explicit settings, else the query, else LLM."""
        settings = settings or {}
        raw = settings.get("keywords")
        if raw:
            if isinstance(raw, str):
                return [k.strip() for k in re.split(r"[,，;；]", raw) if k.strip()]
            return [str(k).strip() for k in raw if str(k).strip()]

        kws = self._regex_keywords(query or "")
        if len(kws) < 3 and self._model is not None:
            kws = self._llm_keywords(query or "") or kws
        return kws[:8]

    @staticmethod
    def _regex_keywords(text: str) -> list[str]:
        # Split on CJK/whitespace/punctuation, drop stopwords and 1-char CJK.
        tokens = re.split(r"[\s,，、;；:：/()（）\[\]【】\"']+", text or "")
        out: list[str] = []
        for t in tokens:
            t = t.strip()
            if not t:
                continue
            low = t.casefold()
            if low in _EN_STOP or t in _ZH_STOP:
                continue
            if len(t) < 2 and re.match(r"[A-Za-z]", t):
                continue
            if t not in out:
                out.append(t)
        return out

    def _llm_keywords(self, text: str) -> list[str]:
        prompt = (
            "List 3-6 core scientific keywords from the query, comma-separated, "
            "no numbering, no explanation.\n\nQuery: " + text[:1000]
        )
        try:
            resp = self._model.invoke(prompt)
            raw = getattr(resp, "content", str(resp))
            return [k.strip() for k in re.split(r"[,，\n]", raw) if k.strip()][:8]
        except Exception as exc:
            logger.debug(f"keyword LLM extract failed: {exc}")
            return []

    # -- coverage -----------------------------------------------------------
    def compute(self, source: dict, keywords: list[str]) -> KeywordCov:
        """Compute keyword coverage; never raises."""
        cov = KeywordCov(total=len(keywords))
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
        full = first_nonempty(source, ("full_content", "body", "content"))
        if full and len(str(full)) > 200:
            return str(full), "fulltext"
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
