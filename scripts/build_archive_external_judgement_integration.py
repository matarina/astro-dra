#!/usr/bin/env python3
"""Integrate two model-assisted review outputs without overwriting the blind packet."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "evaluation/archive-claim-review-20261112"
SAMPLE = ROOT / "evaluation/archive-claim-review-sample-20261112.json"
CHATGPT = REVIEW_DIR / "external-chatgpt-response-20261112.txt"
GROK = REVIEW_DIR / "external-grok-output-20261112.txt"
OUT_JSON = REVIEW_DIR / "external-judgement-integration-20261112.json"
OUT_MD = REVIEW_DIR / "external-judgement-integration-20261112.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_chatgpt() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in CHATGPT.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^(immune|if)_", line) or " | " not in line:
            continue
        parts = line.split(" | ", 5)
        if len(parts) != 6:
            raise ValueError(f"cannot parse ChatGPT row: {line}")
        rows.append(
            {
                "blind_id": parts[0],
                "claim_id": int(parts[1]),
                "verdict": parts[2],
                "confidence": parts[3],
                "supporting_quotation": parts[4],
                "explanation": parts[5],
            }
        )
    return rows


def parse_grok() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^(.*?),\s*(\d+),\s*(supported|partially supported|unsupported|contradicted|unverifiable),\s*"
        r"(high|medium|low),\s*(.*)$"
    )
    for line in GROK.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            raise ValueError(f"cannot parse Grok row: {line}")
        rest = match.group(5)
        if rest.startswith("none, "):
            quote, explanation = "none", rest[6:]
        elif rest.startswith('"'):
            closing = rest.rfind('", ')
            if closing < 1:
                raise ValueError(f"cannot split Grok quotation: {line}")
            quote, explanation = rest[: closing + 1], rest[closing + 3 :]
        else:
            raise ValueError(f"Grok quotation has unexpected form: {line}")
        rows.append(
            {
                "blind_id": match.group(1),
                "claim_id": int(match.group(2)),
                "verdict": match.group(3),
                "confidence": match.group(4),
                "supporting_quotation": quote,
                "explanation": explanation,
            }
        )
    return rows


def integration_status(a: str, b: str) -> str:
    if a == b:
        return f"consensus:{a}"
    if {a, b} == {"supported", "partially supported"}:
        return "conservative:partially supported"
    if {a, b} == {"unsupported", "unverifiable"}:
        return "conservative:unverifiable"
    return "disagreement_requires_human_review"


def main() -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    sample_claims = {
        (arm["blind_id"], int(claim["claim_id"])): claim
        for arm in sample["arms"]
        for claim in arm["claims"]
    }
    chat = parse_chatgpt()
    grok = parse_grok()
    assert len(chat) == len(grok) == 48, (len(chat), len(grok))
    chat_map = {(r["blind_id"], r["claim_id"]): r for r in chat}
    grok_map = {(r["blind_id"], r["claim_id"]): r for r in grok}
    assert set(chat_map) == set(grok_map) == set(sample_claims), "review rows do not bind to sample exactly"

    entries: list[dict[str, Any]] = []
    for key in sample_claims:
        claim = sample_claims[key]
        c = chat_map[key]
        g = grok_map[key]
        entries.append(
            {
                "blind_id": key[0],
                "claim_id": key[1],
                "claim_text": claim["text"],
                "claim_kind": claim.get("kind"),
                "citations": claim.get("citations", []),
                "chatgpt_pro": c,
                "grok_manual": g,
                "agreement": c["verdict"] == g["verdict"],
                "integration_status": integration_status(c["verdict"], g["verdict"]),
            }
        )

    statuses = Counter(e["integration_status"] for e in entries)
    payload = {
        "schema_version": "archive_claim_external_judgement_integration.v1",
        "status": "model_assisted_unadjudicated",
        "sample_sha256": sha256(SAMPLE),
        "packet_sha256": "51eb485fef93928912f94b104261cbda34b5c19511319ac926213eb84efb6a94",
        "provenance": {
            "chatgpt": {
                "raw_response": "external-chatgpt-response-20261112.txt",
                "interface": "Archma Firefox via CUA desktop clipboard route",
                "visible_model_setting": "Pro",
                "prompt": "external-review-prompt-20261112.txt",
            },
            "grok": {
                "raw_response": "external-grok-output-20261112.txt",
                "interface": "user-supplied manual transcription from Archma Grok tab",
                "prompt": "external-review-prompt-20261112.txt",
            },
        },
        "integration_rule": {
            "same_verdict": "consensus:<verdict>",
            "supported_vs_partially_supported": "conservative:partially supported",
            "unsupported_vs_unverifiable": "conservative:unverifiable",
            "other_disagreement": "disagreement_requires_human_review",
            "note": "Integration status is not an independent reviewer verdict and never overwrites the blank review README fields.",
        },
        "counts": {
            "claims": len(entries),
            "exact_agreement": sum(e["agreement"] for e in entries),
            "disagreement": sum(not e["agreement"] for e in entries),
            "integration_status": dict(statuses),
            "chatgpt_verdicts": dict(Counter(e["chatgpt_pro"]["verdict"] for e in entries)),
            "grok_verdicts": dict(Counter(e["grok_manual"]["verdict"] for e in entries)),
        },
        "claims": entries,
        "limitations": [
            "Both outputs are model-assisted assessments, not independent biomedical expert review.",
            "The Grok raw output was supplied manually by the user and was not independently captured by this turn's CUA session.",
            "Grok and ChatGPT reported some external verification; supplied-material and externally verified evidence are not the same denominator.",
            "Agreement is not proof of biomedical correctness, and disagreement is not proof of either model being wrong.",
            "The 48-claim sample cannot establish an overall hallucination rate.",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# External model-assisted claim review integration",
        "",
        "This file compares two model-assisted passes over the preserved blinded 48-claim sample. It is separate from the blank independent-review README and does not fill reviewer verdict fields.",
        "",
        "- [Blank independent-review README](README.md)",
        "- [Raw ChatGPT Pro response](external-chatgpt-response-20261112.txt)",
        "- [Raw Grok output supplied by the user](external-grok-output-20261112.txt)",
        "- [Common review prompt](external-review-prompt-20261112.txt)",
        "- [Machine-readable integration](external-judgement-integration-20261112.json)",
        "",
        "## Provenance and interpretation",
        "",
        "ChatGPT was run through the Archma Firefox session with the visible **Pro** setting. The Grok result below is the user-supplied manual output from the Grok tab. Both were asked to review the same compact blinded prompt and supplied evidence excerpts. Their outputs remain model-assisted and are not a substitute for independent biomedical adjudication.",
        "",
        "Integration is deliberately conservative: identical verdicts are recorded as consensus; supported versus partially supported becomes conservative partial support; unsupported versus unverifiable becomes conservative unverifiable; all other conflicts remain `disagreement_requires_human_review`. These statuses are bookkeeping, not new scientific labels.",
        "",
        "## Aggregate comparison",
        "",
        f"- Claims compared: **{len(entries)}**",
        f"- Exact verdict agreement: **{statuses.get('consensus:supported', 0) + statuses.get('consensus:partially supported', 0) + statuses.get('consensus:unsupported', 0) + statuses.get('consensus:contradicted', 0) + statuses.get('consensus:unverifiable', 0)} / 48**",
        f"- Disagreements requiring explicit reconciliation: **{sum(1 for e in entries if not e['agreement'])}**",
        f"- Conservative supported/partial combinations: **{statuses.get('conservative:partially supported', 0)}**",
        f"- Other conflicts left for human review: **{statuses.get('disagreement_requires_human_review', 0)}**",
        "",
        "## Claim-by-claim comparison",
        "",
        "| # | Blind report ID | Claim ID | ChatGPT Pro | Grok | Integration status |",
        "|---:|---|---:|---|---|---|",
    ]
    for i, e in enumerate(entries, 1):
        lines.append(f"| {i} | `{e['blind_id']}` | `{e['claim_id']}` | {e['chatgpt_pro']['verdict']} ({e['chatgpt_pro']['confidence']}) | {e['grok_manual']['verdict']} ({e['grok_manual']['confidence']}) | `{e['integration_status']}` |")
    lines.extend(["", "## Detailed records", ""])
    for i, e in enumerate(entries, 1):
        lines.extend(
            [
                f"### {i:02d}. `{e['blind_id']}` / claim `{e['claim_id']}`",
                "",
                "**Exact claim text:**",
                "",
                "```text",
                e["claim_text"],
                "```",
                "",
                f"- Citations recorded: {', '.join('[' + str(x) + ']' for x in e['citations']) if e['citations'] else 'none'}",
                f"- ChatGPT Pro: **{e['chatgpt_pro']['verdict']}** ({e['chatgpt_pro']['confidence']}); quotation: {e['chatgpt_pro']['supporting_quotation']}; explanation: {e['chatgpt_pro']['explanation']}",
                f"- Grok: **{e['grok_manual']['verdict']}** ({e['grok_manual']['confidence']}); quotation: {e['grok_manual']['supporting_quotation']}; explanation: {e['grok_manual']['explanation']}",
                f"- Integration status: `{e['integration_status']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
            "- Both outputs are model-assisted assessments, not independent biomedical expert review.",
            "- The Grok result is preserved as user-supplied manual text; this turn did not independently capture it from the browser.",
            "- External verification and supplied-material review are different evidence conditions and should not be pooled without a preregistered rule.",
            "- Agreement does not establish correctness; conflicts identify claims needing human adjudication.",
            "- This sample cannot establish an overall hallucination rate.",
        ]
    )
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({"status": "built", "claims": len(entries), "exact_agreement": sum(e["agreement"] for e in entries), "disagreements": sum(not e["agreement"] for e in entries), "json": str(OUT_JSON), "markdown": str(OUT_MD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
