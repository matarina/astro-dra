"""Census preserved author JSONL data without filtering nulls or duplicate IDs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def census(path):
    ids, types = Counter(), Counter()
    rows = nulls = contexts = 0
    # Binary iteration frames records on LF only. str.splitlines() would also
    # split U+2028/U+2029 inside otherwise valid JSON string values.
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{number}: expected an object")
            rows += 1
            ids[str(row.get("id"))] += 1
            types[str(row.get("question_type"))] += 1
            nulls += row.get("answer") is None
            contexts += bool(row.get("context"))
    return {"rows": rows, "unique_ids": len(ids),
            "duplicate_id_rows_beyond_first": sum(n - 1 for n in ids.values()),
            "null_answers": nulls, "question_types": dict(types),
            "nonempty_contexts": contexts, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve existing measurement; choose a new output")
    paths = sorted((args.root / "data").glob("*.jsonl"))
    if not paths:
        raise ValueError("No raw JSONL files")
    result = {path.stem: census(path) for path in paths}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({name: {key: row[key] for key in ["rows", "unique_ids", "null_answers"]}
                      for name, row in result.items()}))
