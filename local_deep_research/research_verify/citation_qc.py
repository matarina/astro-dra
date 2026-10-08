"""Requirement 4 -- claim traceability / anti-hallucination QC.

Extracts factual claims (with their ``[N]`` citations) from the report body and
asks a judge model (temperature=0) whether each cited source's text actually
supports the claim.  Verdicts::

    supported | partial | unsupported | unverifiable

``unsupported`` claims keep their inline text but get a "⚠️缺少支撑" marker;
``unverifiable`` means the source text could not be retrieved (never claimed as
checked).  The rendered section is appended to the report and also returned as
JSON for audit.

The judge is the strategy's own model by default (same endpoint as
``LDR_BENCHMARK_EVALUATION_MODEL``); building a strict temperature=0 client is
optional via :func:`build_judge_model`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from loguru import logger

from .config import VerifyConfig, get_config
from .models import ClaimCheck
from .textutil import first_nonempty, truncate

# A claim line carries one or more [N] / [N, M] citation markers.
_CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_SENT_SPLIT = re.compile(r"(?<=[。.!?！？])\s+")

VERDICTS = {"supported", "partial", "unsupported", "unverifiable"}


@dataclass
class Claim:
    text: str
    citations: list[int] = field(default_factory=list)


class CitationQc:
    """Extract claims, retrieve cited fragments, judge support."""

    def __init__(self, judge_model=None, cfg: VerifyConfig | None = None) -> None:
        self._judge = judge_model
        self._cfg = cfg or get_config()

    # -- extraction ---------------------------------------------------------
    def extract_claims(self, report_text: str) -> list[Claim]:
        """Return sentence-level claims that carry at least one citation."""
        claims: list[Claim] = []
        # Drop the auto-appended Sources/verification sections to avoid noise.
        body = re.split(r"\n##\s+Sources\b", report_text or "")[0]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for sentence in _SENT_SPLIT.split(stripped):
                cites = _CITE_RE.findall(sentence)
                if not cites:
                    continue
                nums: list[int] = []
                for group in cites:
                    for n in group.split(","):
                        n = n.strip()
                        if n.isdigit():
                            nums.append(int(n))
                if not nums:
                    continue
                claims.append(Claim(text=sentence.strip(), citations=sorted(set(nums))))
        return claims

    # -- checking -----------------------------------------------------------
    def check(
        self, claims: list[Claim], collector, batch: int | None = None
    ) -> list[ClaimCheck]:
        """Judge each claim against its cited source fragments."""
        if not claims:
            return []
        batch = batch or self._cfg.qc_batch_size
        out: list[ClaimCheck] = []
        for i in range(0, len(claims), batch):
            for claim in claims[i : i + batch]:
                out.append(self._check_one(claim, collector))
        return out

    def _check_one(self, claim: Claim, collector) -> ClaimCheck:
        sources, fragments, keys = [], [], []
        for n in claim.citations:
            src = collector.find_by_index(n) if collector is not None else None
            if not src:
                continue
            keys.append(str(first_nonempty(src, ("doi", "link", "url", "pmid")) or n))
            frag = first_nonempty(src, ("full_content", "abstract", "snippet", "body"))
            if frag:
                fragments.append(truncate(str(frag), 1500))

        check = ClaimCheck(claim=claim.text, citations=claim.citations, sources=keys)
        if not fragments:
            check.verdict = "unverifiable"
            check.reason = "被引文献原文不可得"
            return check

        if self._judge is None:
            check.verdict = "unverifiable"
            check.reason = "无判卷模型"
            return check

        verdict, fragment, reason = self._judge_claim(claim.text, fragments)
        check.verdict = verdict if verdict in VERDICTS else "unverifiable"
        check.supporting_fragment = fragment
        check.reason = reason
        return check

    def _judge_claim(self, claim: str, fragments: list[str]) -> tuple[str, str | None, str]:
        joined = "\n---\n".join(f"[{i + 1}] {f}" for i, f in enumerate(fragments))
        prompt = (
            "You are a strict scientific fact-checker. Decide whether the CITED "
            "source fragments support the CLAIM. Reply with strict JSON:\n"
            '{"verdict":"supported|partial|unsupported|unverifiable",'
            '"supporting_fragment":"<quote or empty>","reason":"<short>"}\n'
            "Use 'unverifiable' only if fragments are empty/irrelevant. "
            "Do not use outside knowledge.\n\n"
            f"CLAIM: {claim}\n\nCITED FRAGMENTS:\n{joined}"
        )
        try:
            resp = self._judge.invoke(prompt)
            raw = getattr(resp, "content", str(resp))
            data = json.loads(_extract_json(raw))
            return (
                str(data.get("verdict", "unverifiable")).lower(),
                data.get("supporting_fragment") or None,
                str(data.get("reason", "")),
            )
        except Exception as exc:
            logger.debug(f"citation_qc judge failed: {exc}")
            return "unverifiable", None, f"judge_error:{exc}"

    # -- rendering ----------------------------------------------------------
    @staticmethod
    def render_section(checks: list[ClaimCheck]) -> str:
        if not checks:
            return ""
        badge = {
            "supported": "✅有支撑",
            "partial": "⚠️部分支撑",
            "unsupported": "❌缺少支撑",
            "unverifiable": "❓未能核对",
        }
        lines = [
            "### 结论可溯源性核查",
            "",
            "| 结论 | 引用 | 判定 | 说明 |",
            "|------|------|------|------|",
        ]
        for c in checks:
            claim = c.claim[:90].replace("|", "/").replace("\n", " ")
            cites = ",".join(str(n) for n in c.citations)
            reason = (c.reason or "").replace("|", "/")[:100]
            lines.append(
                f"| {claim} | [{cites}] | {badge.get(c.verdict, c.verdict)} | {reason} |"
            )
        return "\n".join(lines)

    @staticmethod
    def apply_inline_markers(report_text: str, checks: list[ClaimCheck]) -> str:
        """Append '⚠️缺少支撑' right after unsupported claim sentences."""
        unsupported = [c.claim for c in checks if c.verdict == "unsupported"]
        out = report_text
        for claim in unsupported:
            if claim and claim in out:
                out = out.replace(claim, claim + " ⚠️缺少支撑", 1)
        return out


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip())
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start : end + 1] if start != -1 and end != -1 else raw


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="research_verify citation QC (extract only)")
    parser.add_argument("--text", required=True)
    args = parser.parse_args(argv)
    claims = CitationQc().extract_claims(args.text)
    for c in claims:
        print(json.dumps({"claim": c.text, "citations": c.citations}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
