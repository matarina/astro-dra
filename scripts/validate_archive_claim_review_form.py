#!/usr/bin/env python3
"""Validate the unlabeled archive claim-review form binding."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--form", type=Path, required=True)
    args = parser.parse_args()
    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    form = json.loads(args.form.read_text(encoding="utf-8"))
    if form.get("source_sample_sha256") != digest(args.sample):
        raise ValueError("sample binding changed")
    expected = []
    for arm in sample["arms"]:
        for claim in arm["claims"]:
            expected.append((arm["case_id"], arm["blind_id"], claim["claim_id"]))
    actual = [(row.get("case_id"), row.get("blind_id"), row.get("claim_id"))
              for row in form.get("rows", [])]
    if sorted(actual) != sorted(expected):
        raise ValueError("form rows differ from sample")
    for row in form["rows"]:
        assessment = row.get("assessment") or {}
        if any(value is not None for value in assessment.values()):
            raise ValueError("form already contains an assessment label")
    print(json.dumps({"status": "valid_unlabeled_form", "rows": len(actual),
                      "sample_sha256": digest(args.sample),
                      "form_sha256": digest(args.form)}))


if __name__ == "__main__":
    main()
