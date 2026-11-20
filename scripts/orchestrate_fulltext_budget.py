"""Run matched development or reserved full-text pairs in disposable containers."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", choices=["development", "reserved"], required=True)
    args = parser.parse_args()
    root = args.root
    cfg = json.loads((root / "experiment.json").read_text())
    cases = [c for c in cfg["cases"] if c["split"] == args.phase and
             (args.phase == "reserved" or c["variant"] == "original")]
    logs = root / "execution"
    logs.mkdir(exist_ok=True)
    def pair(item):
        position, case = item
        order = ["baseline", "candidate"] if position % 2 == 0 else ["candidate", "baseline"]
        for arm in order:
            dest = logs / (arm + "-" + case["case_id"] + ".json")
            if dest.exists():
                continue
            name = "ldr-fulltext-" + arm + "-" + case["case_id"].replace("_", "-")
            command = ["docker", "run", "--rm", "--no-healthcheck", "--name", name,
                       "--network", "host", "--add-host", "host.docker.internal:127.0.0.1",
                       "--env-file", "/tmp/ldr-live-env-auth-0600", "-e", "PYTHONDONTWRITEBYTECODE=1",
                       "-e", "PILOT_ARM=" + arm, "-e", "PILOT_CASE_ID=" + case["case_id"],
                       "-v", str(root) + ":/experiment", "-v", str(root / "run-code") + ":/workspace:ro",
                       "--entrypoint", "/install/.venv/bin/python", cfg["immutable_image_id"],
                       "/workspace/scripts/fulltext_budget_report_boot.py"]
            begin = time.time()
            with (logs / (arm + "-" + case["case_id"] + ".log")).open("w") as output:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
            record = {"arm": arm, "case_id": case["case_id"], "phase": args.phase,
                      "position": position, "pair_order": order, "started_unix": begin,
                      "ended_unix": time.time(), "exit_code": result.returncode,
                      "image_id": cfg["immutable_image_id"]}
            dest.write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(record), flush=True)
            if result.returncode:
                raise RuntimeError("Terminal bootstrap failure, preserved: " + arm + " " + case["case_id"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(pair, enumerate(cases)))


if __name__ == "__main__":
    main()
