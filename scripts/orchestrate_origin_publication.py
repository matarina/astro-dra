"""Counterbalanced three-arm regression in disposable, verified containers."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    root = parser.parse_args().root
    cfg = json.loads((root / "experiment.json").read_text())
    logs = root / "execution"
    logs.mkdir(exist_ok=True)
    def run(item):
        position, case = item
        arms = cfg["arms"]
        order = arms[position % 3:] + arms[:position % 3]
        for arm in order:
            destination = logs / (arm + "-" + case["case_id"] + ".json")
            if destination.exists():
                raise ValueError("Preserve prior execution rather than silently rerunning")
            name = "ldr-origin-" + arm + "-" + case["case_id"].replace("_", "-")
            command = ["docker", "run", "--rm", "--no-healthcheck", "--name", name,
                       "--network", "host", "--add-host", "host.docker.internal:127.0.0.1",
                       "--env-file", "/tmp/ldr-live-env-auth-0600",
                       "-e", "HOME=/tmp/ldr-origin-home", "-e", "XDG_CACHE_HOME=/tmp/ldr-origin-cache",
                       "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PILOT_ARM=" + arm,
                       "-e", "PILOT_CASE_ID=" + case["case_id"], "-v", str(root) + ":/experiment",
                       "-v", str(root / "run-code") + ":/workspace:ro", "--entrypoint", "/install/.venv/bin/python",
                       cfg["immutable_image_id"], "/workspace/scripts/fulltext_budget_report_boot.py"]
            started = time.time()
            with (logs / (arm + "-" + case["case_id"] + ".log")).open("w") as output:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
            record = {"case_id": case["case_id"], "arm": arm, "position": position, "order": order,
                      "exit_code": result.returncode, "started_unix": started, "ended_unix": time.time()}
            destination.write_text(json.dumps(record, indent=2) + "\n")
            print(json.dumps(record), flush=True)
            if result.returncode:
                raise RuntimeError("Terminal bootstrap failure, retain logs")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, enumerate(cfg["cases"])))


if __name__ == "__main__":
    main()
