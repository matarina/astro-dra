"""Validate the frozen, cross-domain evidence evaluation manifest."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/heldout-evaluation-20261110.json"


def validate(path: Path = MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    domains = Counter(case["domain"] for case in cases)
    variants = Counter(case["variant"] for case in cases)
    assert data["status"] == "design_scaffold_not_sealed_holdout"
    assert len(ids) == len(set(ids)) == 24
    assert set(domains) == {"biomedical", "climate", "astronomy", "software", "history", "law"}
    assert variants == {"direct": 6, "paraphrase": 6, "adversarial": 12}
    assert data["fixed_run"] == {
        "same_model": True,
        "same_temperature": True,
        "same_iteration_budget": True,
        "same_source_pack": True,
        "same_proxy_and_timeout": True,
        "production_changes": False,
    }
    return {"status": "structure_valid_only", "heldout_ready": False, "case_count": len(cases), "domains": dict(domains), "variants": dict(variants)}


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
