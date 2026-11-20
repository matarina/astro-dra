"""Replay sealed baseline finalization with and without the legacy constraint call.

Run inside the pinned evaluation image with the sealed run mounted read-only
at /frozen and an empty writable directory at /output. The original runner
sees a private /experiment with only the sealed inputs and replay outputs.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from types import SimpleNamespace


FROZEN = Path("/frozen")
OUT = Path("/output")
EXPERIMENT = Path("/experiment")
CONSTRAINT_PREFIX = "Extract publication constraints from the query as strict JSON"


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fingerprint(value):
    return sha256(str(value).encode()).hexdigest()


def replay_case(case_id, bypass):
    from local_deep_research.config import llm_config
    from research_verify import evidence_flow
    from research_verify.constraint_matcher import ConstraintMatcher

    expected = read(FROZEN / "baseline" / f"{case_id}.calls.json")
    if not expected[0]["prompt"].startswith(CONSTRAINT_PREFIX):
        raise ValueError("The archived first call is not the constraint fallback")
    minutes = [minute for event in expected for minute in re.findall(
        r"(?m)^Current time is ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}) UTC\.$", event["prompt"])]
    if len(minutes) != 1:
        raise ValueError("Expected one archived writer time")
    archived_time = datetime.strptime(minutes[0], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)

    class WriterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return archived_time.astimezone(tz) if tz else archived_time.replace(tzinfo=None)

    evidence_flow.datetime = WriterClock
    expected = expected[1:] if bypass else expected
    cursor = 0
    mismatches = []

    class ReplayModel:
        def invoke(self, prompt, *args, **kwargs):
            nonlocal cursor
            actual = str(prompt)
            if cursor >= len(expected) or actual != expected[cursor]["prompt"]:
                want = expected[cursor]["prompt"] if cursor < len(expected) else None
                mismatches.append({"position": cursor, "expected_sha256": fingerprint(want),
                                   "actual_sha256": fingerprint(actual)})
                raise ValueError("Archived prompt differs from replay prompt")
            archived = expected[cursor]
            cursor += 1
            if archived["status"] != "completed":
                raise ValueError("Archived model call did not complete")
            return SimpleNamespace(content=archived["response"], usage_metadata=archived["usage"])

    llm_config.get_llm = lambda *args, **kwargs: ReplayModel()
    if bypass:
        ConstraintMatcher._try_llm_parse = lambda self, text, constraint: None
    os.environ.update(PILOT_CASE_ID=case_id, PILOT_ARM="baseline")
    runpy.run_path(str(FROZEN / "run-code/scripts/run_fulltext_budget_report.py"), run_name="__main__")
    record = read(EXPERIMENT / "baseline" / f"{case_id}.json")
    original = read(FROZEN / "baseline" / f"{case_id}.json")
    keys = ("status", "body", "sources", "final_report", "publication", "settings_sha256", "source_pack_sha256")
    same = {key: key in record and record[key] == original[key] for key in keys}
    return dict(case_id=case_id, exact_calls=cursor, expected_calls=len(expected), prompt_mismatches=mismatches,
                status=record["status"], same=same,
                matched=all(same.values()) and not mismatches and cursor == len(expected))


def main():
    if len(sys.argv) == 3:
        result = replay_case(sys.argv[1], sys.argv[2] == "bypass")
        write(EXPERIMENT / f"{sys.argv[1]}.receipt.json", result)
        return

    cfg = read(FROZEN / "experiment.json")
    cases = [case["case_id"] for case in cfg["cases"] if case["split"] == "reserved"]
    code = FROZEN / "baseline-code"
    subprocess.run([sys.executable, str(code / "deployment/install_overlays.py"), "--source",
                    str(code / "local_deep_research"), "--manifest", str(FROZEN / "baseline-install-manifest.json")],
                   check=True, stdout=subprocess.DEVNULL)
    if EXPERIMENT.exists():
        raise FileExistsError(EXPERIMENT)
    for mode in ("control", "bypass"):
        target = OUT / mode
        target.mkdir()
        os.chown(target, OUT.stat().st_uid, OUT.stat().st_gid)
        (target / "experiment.json").symlink_to(FROZEN / "experiment.json")
        (target / "source-packs").symlink_to(FROZEN / "source-packs")
        EXPERIMENT.symlink_to(target, target_is_directory=True)
        def run(case):
            with (target / f"{case}.process.log").open("w") as log:
                process = subprocess.run([sys.executable, __file__, case, mode], stdout=log,
                                         stderr=subprocess.STDOUT, timeout=60,
                                         user=target.stat().st_uid, group=target.stat().st_gid)
            receipt = target / f"{case}.receipt.json"
            return read(receipt) if receipt.is_file() else {"case_id": case, "exit_code": process.returncode,
                                                           "matched": False}
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                rows = list(pool.map(run, cases))
        finally:
            EXPERIMENT.unlink()
        write(target / "results.json", rows)
        print(json.dumps({"mode": mode, "scheduled": len(cases), "matched": sum(row["matched"] for row in rows),
                          "same_fields": dict(sum((Counter(key for key, ok in row.get("same", {}).items() if ok)
                                                   for row in rows), Counter()))}), flush=True)


if __name__ == "__main__":
    main()
