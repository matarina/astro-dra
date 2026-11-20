"""Wait on a confirmed generation process, then run the frozen assessment phase."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--generation-pid",type=int,required=True)
    args=parser.parse_args();root=args.root
    process=Path("/proc")/str(args.generation_pid)
    cmdline=(process/"cmdline").read_bytes()
    if b"orchestrate_benchmark_reports.py" not in cmdline or str(root).encode() not in cmdline:
        raise ValueError("Generation PID is not the expected live experiment")
    identity=(process/"stat").read_text().split()[21]
    cfg=json.loads((root/"experiment.json").read_text())
    paths=[root/arm/(c["case_id"]+".json") for arm in ["baseline","candidate"] for c in cfg["cases"]]
    while not all(p.exists() for p in paths):
        if not process.exists() or (process/"stat").read_text().split()[21]!=identity:
            raise RuntimeError("Generation ended before all scheduled results; inspect terminal evidence, do not restart")
        time.sleep(5)
    manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (root/"assessment-drafts-hashes.json").write_text(json.dumps(manifest,indent=2)+"\n")
    def run(shard):
        name="ldr-benchmark-assess-1111-"+str(shard)
        command=["docker","run","--rm","--no-healthcheck","--name",name,"--network","host",
            "--add-host","host.docker.internal:127.0.0.1","--env-file","/tmp/ldr-live-env-auth-0600",
            "-e","PYTHONDONTWRITEBYTECODE=1","-e","ASSESS_SHARD="+str(shard),
            "-v",str(root)+":/experiment","-v",str(root/"assessment-code")+":/workspace:ro",
            "--entrypoint","/install/.venv/bin/python","astro-dra:main-20261106",
            "/workspace/scripts/benchmark_assessment_boot.py"]
        with (root/("assessment-"+str(shard)+".log")).open("w") as output:
            result=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
        event={"shard":shard,"exit_code":result.returncode,"ended_unix":time.time()}
        (root/("assessment-"+str(shard)+"-terminal.json")).write_text(json.dumps(event,indent=2)+"\n")
        print(json.dumps(event),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,[0,1]))


if __name__=="__main__":
    main()
