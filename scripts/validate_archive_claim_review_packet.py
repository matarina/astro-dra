#!/usr/bin/env python3
"""Validate frozen archive claim-review packet bindings.

This checks provenance and blinding contracts only. It never labels claims or
infers scientific support.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))["mapping"]
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_cases = {case["case_id"]: case for case in manifest["cases"]}
    packet_cases = {case["case_id"]: case for case in packet["cases"]}
    if set(packet_cases) != set(expected_cases):
        raise ValueError("packet case set differs from manifest")
    map_by_id = {row["blind_id"]: row for row in mapping}
    if len(map_by_id) != len(mapping):
        raise ValueError("duplicate blind_id")
    packet_ids = []
    claim_count = 0
    for case_id, case in packet_cases.items():
        manifest_case = expected_cases[case_id]
        source_path = Path(manifest_case["source_path"])
        source_rows = json.loads(source_path.read_text(encoding="utf-8"))
        source_ids = {int(row["index"]) for row in source_rows if str(row.get("index", "")).isdigit()}
        if case["source_snapshot_sha256"] != digest(source_path):
            raise ValueError(f"source snapshot changed: {case_id}")
        if len(case["arms"]) != len(manifest_case["arms"]):
            raise ValueError(f"arm count changed: {case_id}")
        for arm in case["arms"]:
            blind_id = arm["blind_id"]
            packet_ids.append(blind_id)
            if blind_id not in map_by_id:
                raise ValueError(f"missing mapping: {blind_id}")
            if "arm_label" in arm:
                raise ValueError(f"arm identity leaked in packet: {blind_id}")
            for claim in arm["claims"]:
                claim_count += 1
                for cited in claim.get("citations", []):
                    if cited not in source_ids:
                        raise ValueError(f"citation outside source snapshot: {blind_id}/{cited}")
                for source in claim.get("source_records", []):
                    if int(source["index"]) not in source_ids:
                        raise ValueError(f"source record outside snapshot: {blind_id}")
    if sorted(packet_ids) != sorted(map_by_id):
        raise ValueError("packet/mapping blind IDs differ")
    for row in mapping:
        if row["case_id"] not in expected_cases:
            raise ValueError("mapping case outside manifest")
    print(json.dumps({"status": "valid", "cases": len(packet_cases),
                      "blind_arms": len(packet_ids), "claims": claim_count,
                      "mapping_sha256": digest(args.mapping),
                      "packet_sha256": digest(args.packet)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
