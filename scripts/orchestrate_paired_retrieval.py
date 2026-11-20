"""Issue each frozen query to the two installed arms in a short time window."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    protocol = json.loads((root / "retrieval-protocol.json").read_text())
    schedule = json.loads((root / "retrieval-schedule.json").read_text())
    workers = {}
    with ExitStack() as stack:
        transcript = stack.enter_context((root / "retrieval-worker-transcript.log").open("x"))
        try:
            for arm in ("baseline", "candidate"):
                error_log = stack.enter_context((root / (arm + "-retrieval-stderr.log")).open("x"))
                network_env = []
                if protocol.get("direct_searxng_instance"):
                    host = urlsplit(protocol["searxng_instance"]).hostname
                    network_env = ["-e", "NO_PROXY=" + host, "-e", "no_proxy=" + host]
                command = ["docker", "run", "--rm", "--interactive", "--no-healthcheck",
                           "--name", "ldr-paired-retrieval-" + arm, "--network", "host",
                           "--add-host", "host.docker.internal:127.0.0.1",
                           "--env-file", "/tmp/ldr-live-env-auth-0600", "-e", "PYTHONDONTWRITEBYTECODE=1",
                           "-e", "PILOT_ARM=" + arm, "-e", "PILOT_CASE_ID=retrieval-install",
                           "-e", "LDR_DATA_DIR=/tmp/ldr-paired-retrieval",
                           *network_env,
                           "-v", str(root) + ":/experiment", "-v", str(root / "run-code") + ":/workspace:ro",
                           "--entrypoint", "/install/.venv/bin/python", protocol["image_id"],
                           "/workspace/scripts/retrieval_boot.py"]
                workers[arm] = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                stderr=error_log, text=True, bufsize=1)

            def expect(arm, marker):
                for line in workers[arm].stdout:
                    transcript.write(arm + " " + line)
                    transcript.flush()
                    if line.strip() == marker:
                        return
                raise RuntimeError("Worker output ended before " + arm + " " + marker)

            for arm in workers:
                expect(arm, "READY")
            for position, task in enumerate(schedule):
                order = ("baseline", "candidate") if position % 2 == 0 else ("candidate", "baseline")
                started = time.time()
                for arm in order:
                    workers[arm].stdin.write(json.dumps(task) + "\n")
                    workers[arm].stdin.flush()
                for arm in order:
                    expect(arm, "DONE " + task["case_id"] + " " + task["engine"])
                print(json.dumps({**task, "position": position, "started_unix": started,
                                  "finished_unix": time.time(), "dispatch_order": order}), flush=True)
        finally:
            for process in workers.values():
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
            statuses = {arm: process.wait() for arm, process in workers.items()}
            (root / "retrieval-worker-terminal.json").write_text(json.dumps(statuses, indent=2) + "\n")
    if any(statuses.values()):
        raise RuntimeError("A retrieval worker exited unsuccessfully")


if __name__ == "__main__":
    main()
