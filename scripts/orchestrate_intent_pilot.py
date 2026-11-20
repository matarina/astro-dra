"""Run frozen pair order, with at most two disposable model jobs active."""
import concurrent.futures
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path("/data1/maxw/ldr-evaluation/intent-paired-20261110"))
    root = parser.parse_args().root
    cfg = json.loads((root / "experiment.json").read_text())
    logs = root / "execution"
    logs.mkdir(exist_ok=True)
    def run_pair(item):
        position, case = item
        order = ["baseline", "candidate"] if position % 2 == 0 else ["candidate", "baseline"]
        for arm in order:
            result = root / arm / (case["case_id"] + ".json")
            if result.exists():
                continue
            name = "ldr-intent-" + arm + "-" + case["case_id"].replace("_", "-")
            command = ["docker", "run", "--rm", "--name", name, "--network", "host",
                       "--add-host", "host.docker.internal:127.0.0.1", "--env-file", "/tmp/ldr-live-env-auth-0600",
                       "-e", "PILOT_ARM=" + arm, "-e", "PILOT_CASE_ID=" + case["case_id"],
                       "-v", str(root) + ":/experiment", "-v", str(root / "run-code") + ":/workspace:ro",
                       "--entrypoint", "/install/.venv/bin/python", "astro-dra:main-20261106",
                       "/workspace/scripts/intent_pilot_boot.py"]
            begin = time.time()
            log = logs / (arm + "-" + case["case_id"] + ".log")
            try:
                with log.open("w") as output:
                    proc = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=600)
                event = {"exit_code": proc.returncode}
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                event = {"status": "timed_out"}
            event.update(arm=arm, case_id=case["case_id"], started_unix=begin,
                         ended_unix=time.time(), position=position, pair_order=order)
            (logs / (arm + "-" + case["case_id"] + ".json")).write_text(json.dumps(event, indent=2))
            print(json.dumps(event), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run_pair, enumerate(cfg["cases"])):
            pass


if __name__ == "__main__": main()
