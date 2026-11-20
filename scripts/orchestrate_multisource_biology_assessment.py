"""Freeze all terminal generation artifacts, then run two bounded assessor shards."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    cfg = json.loads((root / "experiment.json").read_text())
    for case in cfg["cases"]:
        for arm in ["baseline", "candidate"]:
            execution = root / "execution" / (arm + "-" + case["case_id"] + ".json")
            if not execution.is_file() or json.loads(execution.read_text())["exit_code"] != 0:
                raise ValueError("Generation has not terminated cleanly: " + str(execution))
            for suffix in [".json", ".calls.json", ".installed.json"]:
                if not (root / arm / (case["case_id"] + suffix)).is_file():
                    raise ValueError("Generation artifact missing")
    def inaccessible(error):
        raise error
    paths = [folder / name for arm in ["baseline", "candidate"]
             for folder, _, names in (root / arm).walk(on_error=inaccessible) for name in names]
    freeze = {"status": "All generation containers terminal before assessment; files unchanged thereafter",
              "created_unix": time.time(), "sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
    destination = root / "generation-artifacts-freeze.json"
    if destination.exists():
        previous = json.loads(destination.read_text())
        if previous["sha256"] != freeze["sha256"]:
            raise ValueError("Generation freeze changed")
    else:
        destination.write_text(json.dumps(freeze, indent=2) + "\n")
    def run(shard):
        command = ["docker", "run", "--rm", "--no-healthcheck", "--name", "ldr-multisource-assess-" + str(shard),
                   "--network", "host", "--add-host", "host.docker.internal:127.0.0.1", "--env-file", "/tmp/ldr-live-env-auth-0600",
                   "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "ASSESS_SHARD=" + str(shard),
                   "-v", str(root) + ":/experiment", "--entrypoint", "/install/.venv/bin/python", cfg["immutable_image_id"],
                   "/experiment/assessment-code/scripts/assess_multisource_biology.py"]
        started = time.time()
        with (root / ("assessment-" + str(shard) + ".log")).open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        record = {"shard": shard, "started_unix": started, "ended_unix": time.time(), "exit_code": result.returncode}
        (root / ("assessment-" + str(shard) + "-terminal.json")).write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record), flush=True)
        if result.returncode:
            raise RuntimeError("Assessor failed; retain raw outputs")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [0, 1]))


if __name__ == "__main__":
    main()
