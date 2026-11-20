"""Explain structural annotation failures without changing their verdicts."""
from collections import Counter
import json
from pathlib import Path
import re


def diagnose(root):
    rows = []
    for path in (root / "assessment").glob("*.json"):
        ann = json.loads(path.read_text())
        if ann.get("status") != "annotation_invalid": continue
        arm,caseid = path.stem.split("-",1)
        draft = json.loads((root / arm / (caseid + ".json")).read_text())["body"]
        raw = path.with_suffix(".response.txt").read_text()
        row = {"arm":arm,"case_id":caseid,"original_status":ann["status"]}
        try:
            data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",raw.strip()))
            claims = data.get("claims")
            if not isinstance(claims,list):raise ValueError("claims not list")
            row.update(raw_claim_count=len(claims),
                       unlocalizable_claim_count=sum(not c.get("text") or c["text"] not in draft for c in claims),
                       invalid_label_count=sum(c.get("grounding") not in {"supported","partial","unsupported","contradicted","unverifiable"} for c in claims),
                       reason="strict_claim_substring_or_schema_validation")
        except (ValueError,TypeError,AttributeError):
            row["reason"] = "unparseable_json_or_claim_schema"
        rows.append(row)
    return {"status":"structural_diagnostic_only_original_annotations_unchanged", "rows":rows,
            "reasons":dict(Counter(x["reason"] for x in rows)),
            "limitation":"No post-hoc normalization or semantic label recovery; invalid annotations remain missing in primary metrics."}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    args = p.parse_args()
    data = diagnose(args.root)
    (args.root / "annotation-diagnostics.json").write_text(json.dumps(data,indent=2))
    print(json.dumps(data["reasons"]))
