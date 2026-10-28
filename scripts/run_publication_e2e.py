#!/usr/bin/env python3
"""Run isolated real-research E2E with existing model credentials held in memory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--output",type=Path,required=True)
p.add_argument("--image",default="astro-dra:advisory-20261016")
p.add_argument("--quick-only",action="store_true")
p.add_argument("--replay-generated",action="store_true")
p.add_argument("--paper-scope",choices=["33567185"])
p.add_argument("--container",default="local_deep_research-local-deep-research-1")
p.add_argument("--install-overlays",action="store_true",help="Install workspace overlays in the disposable test container")
args=p.parse_args()
if args.output.exists():p.error("use a fresh output file")
info=json.loads(subprocess.check_output(["docker","inspect",args.container],text=True))[0]
env=dict(x.split("=",1) for x in info["Config"]["Env"] if "=" in x)
config={"model":env["LDR_LLM_MODEL"],"endpoint":env["LDR_LLM_OPENAI_ENDPOINT_URL"].rstrip("/"),
        "key":env.get("LDR_LLM_OPENAI_ENDPOINT_API_KEY") or "EMPTY",
        "pubmed_key":env.get("LDR_SEARCH_ENGINE_WEB_PUBMED_API_KEY"),"quick_only":args.quick_only,"paper_scope":args.paper_scope,
        "frozen_reports":json.loads((ROOT/"local_deep_research/tests/fixtures/frozen_generated_report_cases.json").read_text()) if args.replay_generated else None}
command=["docker","run","--rm","-i","--network",
         "container:"+args.container if args.install_overlays else "host","--tmpfs","/data:rw,size=512m",
         "-e","LDR_DATA_DIR=/data","-e","PYTHONDONTWRITEBYTECODE=1",
         "-v",str(ROOT)+":/workspace:ro","--entrypoint","/install/.venv/bin/python",
         args.image,"-u","/workspace/scripts/publication_e2e_worker.py"]
process_env=dict(os.environ)
if args.install_overlays:
    script=('import subprocess,sys,runpy; subprocess.run([sys.executable,'
            '"/workspace/deployment/install_overlays.py","--source",'
            '"/workspace/local_deep_research","--manifest",'
            '"/workspace/deployment/overlay-manifest.json"],check=True,stdout=subprocess.DEVNULL); '
            'runpy.run_path("/workspace/scripts/publication_e2e_worker.py",run_name="__main__")')
    command[-1:]=["-c",script]
    for key,value in env.items():
        if key.upper() in {"HTTP_PROXY","HTTPS_PROXY","NO_PROXY"}:
            command[4:4]=["-e",key]
            process_env[key]=value
process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=process_env)
process.stdin.write(json.dumps(config));process.stdin.close()
result=None
failure=None
for line in process.stdout:
    if line.startswith("RESULT "):result=json.loads(line[7:])
    elif line.startswith("FAILURE "):
        failure=json.loads(line[8:]);print(line.strip(),flush=True)
    elif line.startswith(("PROGRESS ","REVIEW ")): print(line.strip(),flush=True)
rc=process.wait()
if rc or result is None:
    args.output.write_text(json.dumps({"checks_passed":False,"exit_code":rc,"failure":failure},indent=2)+"\n")
    raise SystemExit("isolated E2E failed; failure recorded")
result["image_id"]=subprocess.check_output(["docker","image","inspect","--format","{{.Id}}",args.image],text=True).strip()
result["code_commit"]=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
result["working_tree_dirty"]=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip())
result["overlays_installed_in_disposable_container"]=args.install_overlays
result["code_sha256"]={str(f.relative_to(ROOT)):sha256(f.read_bytes()).hexdigest()
                     for f in sorted((ROOT/"local_deep_research/research_verify").glob("*.py"))}
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print("SUMMARY "+json.dumps({"checks_passed":result["checks_passed"],
    "quick_audited":result["quick"]["audited_claims"],"detailed_audited":result["detailed"]["audited_claims"],
    "elapsed_s":result["elapsed_s"]}),flush=True)
