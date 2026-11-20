#!/usr/bin/env python3
"""Validate the blinded 48-claim README against its preserved sample/packet."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "evaluation/archive-claim-review-sample-20261112.json"
PACKET = ROOT / "evaluation/archive-claim-review-packet-20261112.json"
REVIEW_DIR = ROOT / "evaluation/archive-claim-review-20261112"
README = REVIEW_DIR / "README.md"


def text(value: Any) -> str:
    return "" if value is None else str(value)


def source_texts(source: dict[str, Any]) -> list[str]:
    return [text(source.get(k)) for k in ("abstract", "content", "full_content", "fetched_content") if text(source.get(k)).strip() and text(source.get(k)).lower() not in {"none", "null"}]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")
    sample_count = sample.get("sample_claims", 0)
    if isinstance(sample_count, list):
        sample_count = len(sample_count)
    assert sample_count == 48, "sample metadata is not 48"
    expected: list[tuple[str, dict[str, Any]]] = []
    for arm in sample["arms"]:
        for claim in arm["claims"]:
            expected.append((arm["blind_id"], claim))
    assert len(expected) == 48, len(expected)
    assert len(set((b, c["claim_id"], c["text"]) for b, c in expected)) == 48, "sample keys are not unique"
    packet_arm_ids = {a["blind_id"] for case in packet["cases"] for a in case["arms"]}
    assert {b for b, _ in expected} <= packet_arm_ids, "sample blind ID absent from full packet"

    heading_re = re.compile(r"^### Sample (\d+) — `([^`]+)` / claim `([^`]+)`$", re.MULTILINE)
    headings = list(heading_re.finditer(readme))
    assert len(headings) == 48, f"expected 48 README sections, found {len(headings)}"
    seen: set[tuple[str, str]] = set()
    problems: list[str] = []
    for i, (blind_id, claim) in enumerate(expected):
        match = headings[i]
        section_end = headings[i + 1].start() if i + 1 < len(headings) else len(readme)
        section = readme[match.start():section_end]
        key = (match.group(2), match.group(3))
        expected_key = (blind_id, text(claim["claim_id"]))
        assert key == expected_key, f"section {i + 1} key {key} != {expected_key}"
        assert key not in seen, f"duplicate README section {key}"
        seen.add(key)

        # The exact claim block is bounded by the next section heading.  The
        # report window may repeat the claim, so validate the dedicated block.
        exact_start = section.find("#### Exact claim text")
        context_start = section.find("#### Surrounding report context")
        assert exact_start >= 0 and context_start > exact_start, f"claim block missing for {key}"
        exact_block = section[exact_start:context_start]
        assert exact_block.count(text(claim["text"])) == 1, f"exact claim text count != 1 for {key}"

        citations_line = section.split("- **Citation indices recorded:**", 1)[1].split("\n", 1)[0]
        for citation in claim.get("citations", []):
            assert f"[{text(citation)}]" in citations_line, f"citation index missing in README for {key}: {citation}"
        if not claim.get("citations"):
            assert "none" in citations_line, f"empty citation list not rendered for {key}"

        evidence_match = re.search(r"\[local evidence file\]\(([^)]+)\)", section)
        assert evidence_match, f"evidence link missing for {key}"
        evidence_path = REVIEW_DIR / evidence_match.group(1)
        assert evidence_path.is_file(), f"evidence file missing for {key}: {evidence_path}"
        evidence = evidence_path.read_text(encoding="utf-8")
        assert evidence.count(text(claim["text"])) >= 1, f"claim missing from evidence file for {key}"
        for source in claim.get("source_records", []) or []:
            idx = text(source.get("index"))
            assert f"[{idx}]" in section, f"source index [{idx}] missing in README for {key}"
            if text(source.get("title")).strip():
                assert text(source["title"]) in section, f"source title missing in README for {key}: {idx}"
            for field in ("doi", "pmid"):
                value = text(source.get(field)).strip()
                if value and value.lower() not in {"none", "null"}:
                    assert value in section, f"{field} missing in README for {key}: {idx}"
            supplied_url = text(source.get("link")).strip()
            if supplied_url and supplied_url.lower() not in {"none", "null"}:
                assert supplied_url in section, f"supplied URL missing in README for {key}: {idx}"
            for passage in source_texts(source):
                assert passage in evidence, f"supplied passage missing from evidence file for {key}: {idx}"

    assert len(seen) == 48
    assert "../archive-claim-review-packet-20261112.json" in readme, "full packet link missing"
    assert "../archive-claim-review-sample-20261112.json" in readme, "sample link missing"
    assert "supported" in readme and "partially supported" in readme and "unsupported" in readme and "contradicted" in readme and "unverifiable" in readme, "verdict options missing"
    assert "cannot establish an overall hallucination rate" in readme, "sample limitation missing"
    integration_path = REVIEW_DIR / "external-judgement-integration-20261112.json"
    if integration_path.is_file():
        integration = json.loads(integration_path.read_text(encoding="utf-8"))
        disagreements = [e for e in integration.get("claims", []) if not e.get("agreement")]
        unresolved = [e for e in disagreements if e.get("integration_status") == "disagreement_requires_human_review"]
        assert len(disagreements) == 21 and len(unresolved) == 8, "integration disagreement denominator changed"
        assert "外部模型辅助评阅分歧：21条（其中8条需人工复核）" in readme, "disagreement section missing"
        for entry in disagreements:
            key = f"`{entry['blind_id']}` / claim `{entry['claim_id']}`"
            assert key in readme, f"disagreement entry missing from README: {key}"
        for entry in unresolved:
            key = f"`{entry['blind_id']}` / claim `{entry['claim_id']}`"
            assert f"关键冲突/人工核验" in readme and key in readme, f"manual conflict entry missing: {key}"
    adjudication_path = REVIEW_DIR / "human-adjudication-20261112.json"
    if adjudication_path.is_file():
        adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
        assert len(adjudication.get("claims", [])) == 21, "human adjudication must cover 21 disagreements"
        assert "用户提供的21条最终定案（论文事实核验）" in readme, "human adjudication section missing"
        for entry in adjudication["claims"]:
            key = f"`{entry['blind_id']} / {entry['claim_id']}`"
            assert key in readme, f"human adjudication entry missing from README: {key}"
    evidence_files = sorted((REVIEW_DIR / "evidence").glob("claim-*.md"))
    assert len(evidence_files) == 48, f"expected 48 evidence files, found {len(evidence_files)}"
    for path in [README, *evidence_files]:
        rendered = path.read_text(encoding="utf-8")
        assert "/data1/" not in rendered and "/home/" not in rendered, f"private absolute path leaked into {path}"

    manifest = json.loads((REVIEW_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sample_sha256"] == sha256(SAMPLE), "manifest sample hash mismatch"
    assert manifest["packet_sha256"] == sha256(PACKET), "manifest packet hash mismatch"
    print(json.dumps({"status": "valid", "claims": 48, "unique_sections": len(seen), "evidence_files": len(evidence_files), "sample_sha256": sha256(SAMPLE), "packet_sha256": sha256(PACKET)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
