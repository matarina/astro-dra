"""Run counterbalanced frozen report pairs with at most two active model jobs."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    root = parser.parse_args().root
    cfg = json.loads((root/"experiment.json").read_text())
    logs = root/"execution"
    logs.mkdir(exist_ok=True)
    def run_pair(item):
        position,case = item
        order = ["baseline","candidate"] if position%2==0 else ["candidate","baseline"]
        for arm in order:
            dest = logs/(arm+"-"+case["case_id"]+".json")
            if dest.exists():
                # A result/terminal marker is not permission to overwrite failures.
                continue
            name = "ldr-bench-"+arm+"-"+case["case_id"].replace("_","-")
            command = ["docker","run","--rm","--no-healthcheck","--name",name,"--network","host",
                "--add-host","host.docker.internal:127.0.0.1","--env-file","/tmp/ldr-live-env-auth-0600",
                "-e","PYTHONDONTWRITEBYTECODE=1","-e","PILOT_ARM="+arm,"-e","PILOT_CASE_ID="+case["case_id"],
                "-v",str(root)+":/experiment","-v",str(root/"run-code")+":/workspace:ro",
                "--entrypoint","/install/.venv/bin/python","astro-dra:main-20261106",
                "/workspace/scripts/benchmark_report_boot.py"]
            begin = time.time()
            with (logs/(arm+"-"+case["case_id"]+".log")).open("w") as output:
                # No observation timeout or automatic restart. Poll this process/container.
                proc = subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
            event = {"arm":arm,"case_id":case["case_id"],"position":position,"pair_order":order,
                "started_unix":begin,"ended_unix":time.time(),"exit_code":proc.returncode}
            dest.write_text(json.dumps(event,indent=2)+"\n")
            print(json.dumps(event),flush=True)
            if proc.returncode:
                raise RuntimeError("Terminal bootstrap failure: "+arm+" "+case["case_id"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run_pair,enumerate(cfg["cases"])))


if __name__=="__main__":
    main()
