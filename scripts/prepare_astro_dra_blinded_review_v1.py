"""Prepare the arm-blind, two-pass review packet for the saved 36 answers."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import os


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation" / "astro-dra-heldout-v1"
RUN_ROOT = PACKAGE / "runs" / "matched-20261118T052009Z"
REVIEW = PACKAGE / os.environ.get("LDR_REVIEW_DIR", "blinded-review-v1")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def shell(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def validate_saved_pair() -> list[dict]:
    rows = [json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {(row["case_id"], arm) for row in rows for arm in ("baseline", "candidate")}
    actual = []
    for case_id, arm in sorted(expected):
        path = RUN_ROOT / arm / f"{case_id}.json"
        if not path.is_file():
            raise ValueError(f"missing saved answer: {arm}/{case_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "completed" or not data.get("output"):
            raise ValueError(f"incomplete saved answer: {arm}/{case_id}")
        actual.append({"case_id": case_id, "arm": arm, "path": path,
                       "receipt_sha256": digest_path(path),
                       "receipt_response_sha256": data.get("response_sha256"),
                       "output_sha256": digest_bytes(data["output"].encode()),
                       "output_chars": len(data["output"]),
                       "prompt_sha256": data["prompt_sha256"],
                       "source_packet_sha256": data["source_packet_sha256"],
                       "output": data["output"]})
    if len(actual) != 36 or {(row["case_id"], row["arm"]) for row in actual} != expected:
        raise ValueError("saved answer denominator mismatch")
    return actual


def writer_visible_source(packet_path: Path) -> tuple[list[dict], str]:
    """Reconstruct the exact source view emitted by run_astro_dra_heldout_v1."""
    raw = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    visible = [{"source_id": item["source_id"], "title": item.get("title", ""),
                "source_type": item.get("source_type", "unknown"),
                "content_type": item.get("content_type", "unknown"),
                "text": item["text"]} for item in raw]
    material = "\n\n".join(
        f"SOURCE {item['source_id']}\n"
        f"Title: {item.get('title','')}\n"
        f"Type: {item.get('source_type','unknown')}\n"
        f"Content basis: {item.get('content_type','unknown')}\n"
        f"Text:\n{item['text']}"
        for item in visible
    )
    return visible, material


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    saved = validate_saved_pair()
    if REVIEW.exists():
        raise SystemExit(f"Review packet already exists. Refusing to overwrite: {REVIEW}")
    REVIEW.mkdir(parents=True, mode=0o700)
    packets = REVIEW / "pass1_packets"
    pass2 = REVIEW / "pass2_gold"
    private = REVIEW / "private"
    forms = REVIEW / "review_forms"
    for path in (packets, pass2, private, forms):
        path.mkdir(mode=0o700, exist_ok=True)

    manifest_rows = {row["case_id"]: row for row in
                     (json.loads(line) for line in (PACKAGE / "manifest.public.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    shuffled = list(saved)
    secrets.SystemRandom().shuffle(shuffled)
    arm_key = {}
    pass1_rows = []
    pass2_rows = []
    for row in shuffled:
        opaque = "R" + secrets.token_hex(10)
        case_id = row["case_id"]
        public_row = manifest_rows[case_id]
        source_packet = PACKAGE / public_row["source_packet_path"]
        prompt = PACKAGE / public_row["prompt_path"]
        packet_dir = packets / opaque
        packet_dir.mkdir(mode=0o700)
        (packet_dir / "prompt.md").write_bytes(prompt.read_bytes())
        visible_rows, visible_material = writer_visible_source(source_packet)
        (packet_dir / "source_packet.jsonl").write_text(
            "".join(canonical(item) + "\n" for item in visible_rows), encoding="utf-8")
        (packet_dir / "writer_visible_material.txt").write_text(visible_material, encoding="utf-8")
        (packet_dir / "output.md").write_text(row["output"], encoding="utf-8")
        packet_meta = {
            "opaque_report_id": opaque,
            "prompt_sha256": digest_path(packet_dir / "prompt.md"),
            "source_packet_sha256": digest_path(packet_dir / "source_packet.jsonl"),
            "writer_visible_material_sha256": digest_path(packet_dir / "writer_visible_material.txt"),
            "output_sha256": digest_path(packet_dir / "output.md"),
        }
        write_json(packet_dir / "hashes.json", packet_meta)
        pass1_rows.append({**packet_meta, "review_status": "unreviewed"})

        gold_path = PACKAGE / "gold.private" / f"{case_id}_claim_labels.jsonl"
        gold_rows = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        sanitized = []
        for number, claim in enumerate(gold_rows, 1):
            sanitized.append({
                "gold_claim_id": f"G{number:02d}",
                "claim_text": claim["claim_text"],
                "expected_label": claim["expected_label"],
                "source_ids": claim.get("source_ids", []),
                "exact_locators": claim.get("exact_locators", []),
                "required_scope": claim.get("required_scope", {}),
                "severity": claim.get("severity"),
                "allowed_abstention": claim.get("allowed_abstention"),
                "rationale": claim.get("rationale", ""),
            })
        gold_out = pass2 / f"{opaque}.jsonl"
        gold_out.write_text("".join(canonical(item) + "\n" for item in sanitized), encoding="utf-8")
        pass2_rows.append({"opaque_report_id": opaque, "gold_sha256": digest_path(gold_out),
                           "review_status": "pass2_pending"})
        arm_key[opaque] = {
            "case_id": case_id, "arm": row["arm"],
            "source_packet_path": public_row["source_packet_path"],
            "raw_source_packet_sha256": digest_path(PACKAGE / public_row["source_packet_path"]),
            "prompt_path": public_row["prompt_path"],
            "saved_output_path": str(row["path"].relative_to(ROOT)),
            "saved_receipt_sha256": row["receipt_sha256"],
            "saved_response_sha256": row["receipt_response_sha256"],
        }

        form = {
            "opaque_report_id": opaque,
            "reviewer_id": "",
            "pass1": {
                "assertions": [],
                "no_assertion_case": False,
                "review_complete": False,
            },
            "pass2": {
                "ledger_rows": [],
                "review_complete": False,
            },
            "notes": "",
        }
        write_json(forms / f"{opaque}.json", form)

    write_json(REVIEW / "pass1_manifest.json", {
        "schema_version": "astro_dra_blinded_review_pass1.v1",
        "status": "sealed_before_review",
        "report_count": len(pass1_rows),
        "reports": pass1_rows,
        "gold_visible": False,
        "arm_visible": False,
        "case_id_visible": False,
        "model_assessment_visible": False,
        "source_view": "exact_writer_visible_source_material",
        "raw_source_packets_preserved_for_provenance": True,
    })
    write_json(private / "arm_key.json", {
        "schema_version": "astro_dra_blinded_arm_key.v1",
        "status": "sealed",
        "run_root": str(RUN_ROOT.relative_to(ROOT)),
        "reports": arm_key,
    })
    write_json(private / "pass2_key.json", {
        "schema_version": "astro_dra_blinded_pass2_key.v1",
        "status": "sealed",
        "reports": pass2_rows,
    })
    os.chmod(private / "arm_key.json", 0o600)
    os.chmod(private / "pass2_key.json", 0o600)

    protocol = (
        "# Astro-DRA blinded review protocol v1\n\n"
        "Pass 1 uses one opaque output at a time with its prompt and frozen source packet. "
        "Reviewers inventory every substantive assertion, including off-ledger assertions, "
        "with exact output spans, local citations, source locators, scope, stance, and severity. "
        "Gold labels, case IDs, arm identity, and model assessments are withheld.\n\n"
        "Pass 2 remains arm-blind and adds the sanitized private ledger for required supported "
        "content, omissions, abstention correctness, and edge handling. Disagreements are resolved "
        "before arm unblinding. Use two reviewers per case where feasible and double-review difficult cases.\n\n"
        "Primary metric is the per-case macro-average of deduplicated wrong substantive assertions divided "
        "by all substantive assertions. Track no-assertion cases separately. Secondary metrics cover local "
        "citation alignment, useful-content retention, supported-answer recall, unjustified abstention, "
        "zero-source/conflict handling, and new severe errors.\n"
    )
    (REVIEW / "review_protocol.md").write_text(protocol, encoding="utf-8")
    write_json(REVIEW / "review_schema.json", {
        "schema_version": "astro_dra_blinded_review_schema.v1",
        "assertion": {
            "assertion_id": "opaque-local-id",
            "text": "verbatim output span",
            "start": 0, "end": 1,
            "local_citations": ["SRC-..."],
            "evidence_source_ids": ["SRC-..."],
            "evidence_locators": [{"source_id": "SRC-...", "start": 0, "end": 1, "quote": ""}],
            "scope": {"species": "", "population": "", "tissue": "", "assay": "", "outcome": ""},
            "stance": "reported|inferred|causal|predictive|abstention|unknown",
            "verdict": "supported|partial|wrong|unverifiable|correct_refutation|correct_abstention|hedged",
            "severity": "low|moderate|high|severe",
        },
        "pass2_ledger_row": {
            "gold_claim_id": "G01",
            "output_assertion_ids": [],
            "support": "present|partial|omitted|wrong|unclear",
            "abstention": "correct|incorrect|not_applicable|unclear",
            "citation_alignment": "aligned|misaligned|unverifiable",
            "essential_content": "retained|lost|not_applicable|unclear",
            "notes": "",
        },
    })
    write_json(REVIEW / "promotion_criteria.json", {
        "schema_version": "astro_dra_promotion_guardrails.v1",
        "status": "predeclared_pilot_guardrails",
        "no_new_severe_errors": True,
        "no_invented_sources": True,
        "no_severe_scope_overreach": True,
        "wrong_assertion_rate_delta_max_pp": 5,
        "citation_alignment_rate_delta_min_pp": -5,
        "useful_content_retention_min_ratio": 0.90,
        "essential_item_loss_allowed": False,
        "correct_abstention_all_applicable_edge_cases": True,
        "extra_unjustified_abstention_max": 1,
        "uncertainty_required": True,
        "improvement_claim_requires_measured_reduction": True,
        "final_margins_must_be_locked_before_unblinding": True,
    })

    relevant = [
        "scripts/run_astro_dra_heldout_v1.py", "scripts/assess_astro_dra_heldout_v1.py",
        "scripts/summarize_astro_dra_heldout_v1.py", "local_deep_research/research_verify/generation.py",
        "local_deep_research/research_verify/evidence_grounding.py", "local_deep_research/research_verify/heldout.py",
    ]
    code_files = {path: digest_path(ROOT / path) for path in relevant if (ROOT / path).is_file()}
    freeze = {
        "schema_version": "astro_dra_blinded_review_freeze.v1",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git_head": shell("git", "rev-parse", "HEAD"),
        "git_status_sha256": digest_bytes(shell("git", "status", "--short").encode()),
        "git_diff_sha256": digest_bytes(shell("git", "diff", "HEAD", "--", *relevant).encode()),
        "relevant_code_sha256": code_files,
        "run_root": str(RUN_ROOT.relative_to(ROOT)),
        "run_protocol_sha256": digest_path(RUN_ROOT / "protocol.json"),
        "pass1_report_count": len(pass1_rows),
        "gold_not_in_pass1": True,
        "assessment_not_in_pass1": True,
    }
    write_json(REVIEW / "freeze_manifest.json", freeze)
    print(json.dumps({"review_root": str(REVIEW), "opaque_report_count": len(pass1_rows),
                      "gold_visible_to_pass1": False, "arm_visible_to_pass1": False,
                      "git_head": freeze["git_head"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
