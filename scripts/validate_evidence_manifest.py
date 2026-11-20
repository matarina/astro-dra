"""Validate an ``evidence_grounding.v1`` held-out manifest."""
from __future__ import annotations

import argparse
import json

from research_verify.heldout import validate_manifest, validate_pair_integrity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--require-sealed", action="store_true")
    args = parser.parse_args()
    manifest = validate_manifest(args.manifest, require_sealed=args.require_sealed)
    print(json.dumps({
        "schema_version": manifest.schema_version,
        "status": manifest.status,
        "case_count": len(manifest.cases),
        "cases": [validate_pair_integrity(case) for case in manifest.cases],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
