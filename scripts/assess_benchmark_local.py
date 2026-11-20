"""Cost-bounded local AREX comparison; owns and releases only its vLLM group."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import socket
import subprocess
import time
from urllib.request import build_opener,ProxyHandler,Request

from assess_benchmark_reports import parse,validate_claims


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    args=parser.parse_args();root=args.root
    out=root/"arex-assessment";out.mkdir()
    cfg=json.loads((root/"experiment.json").read_text())
    cases=[c for c in cfg["cases"] if c["domain"]=="bioinformatics" and c["variant"]=="original"]
    if len(cases)!=2:raise ValueError("Unexpected declared subset")
    queue=[(arm,c,method) for arm in ["baseline","candidate"] for c in cases for method in ["grounding","reference_alignment"]]
    random.Random(20261111).shuffle(queue)
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text())}
    for arm,c,_ in queue:
        if json.loads((root/arm/(c["case_id"]+".json")).read_text()).get("status")!="completed":
            raise ValueError("Selected generation not complete")
    with socket.socket() as check:
        check.bind(("127.0.0.1",18473))
    gpu_command=["nvidia-smi","--query-compute-apps=pid,gpu_uuid,used_memory,process_name","--format=csv,noheader"]
    before=subprocess.check_output(gpu_command,text=True)
    (out/"gpu-before.csv").write_text(before)
    previous_pids={int(line.split(",",1)[0]) for line in before.splitlines() if line}
    checkpoint=Path("/data1/maxw/models/AREX-2")
    previous=json.loads(Path("/data1/maxw/ldr-evaluation/arex2-review-20261110/checkpoint-files.json").read_text())
    current={}
    for name in previous["files"]:
        path=checkpoint/name
        current[name]={"bytes":path.stat().st_size,"sha256":sha(path)}
        if current[name]!=previous["files"][name]:raise ValueError("Checkpoint changed since earlier assessment")
    (out/"checkpoint-files.json").write_text(json.dumps(current,indent=2)+"\n")
    venv=Path("/data1/maxw/miniconda3/envs/vllm")
    command=[str(venv/"bin/python"),"-m","vllm.entrypoints.openai.api_server","--host","127.0.0.1","--port","18473",
        "--model",str(checkpoint),"--served-model-name","arex2-eval","--tensor-parallel-size","1",
        "--gpu-memory-utilization","0.68","--max-model-len","16384","--max-num-seqs","1",
        "--max-num-batched-tokens","2048","--enforce-eager","--language-model-only",
        "--default-chat-template-kwargs",'{"enable_thinking": false}']
    protocol={"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"selection":"All two bioinformatics original-question pairs, chosen for small source/context cost before draft inspection; no paraphrase/adversarial or domain-wide claim",
        "order":[[a,c["case_id"],m] for a,c,m in queue],"temperature":0,"max_tokens":6000,"enable_thinking":False,
        "checkpoint_sha256":sha(out/"checkpoint-files.json"),"command":command,"gpu_uuid":"GPU-fc5a0ee0-4821-aa1a-2a1e-5379032f04dc",
        "gpu_sharing":"Existing compute active; memory headroom checked. No process eviction or promise of zero performance cost.",
        "drafts_sha256":{str((root/a/(c["case_id"]+".json")).relative_to(root)):sha(root/a/(c["case_id"]+".json")) for a,c,_ in queue},
        "inputs_sha256":{n:sha(root/n) for n in ["experiment.json","reference-gold.json","assessment-rubric.txt","reference-rubric.txt"]},
        "independence":"Different model family auxiliary assessment, not independent human draft gold; upstream checkpoint equivalence unverified"}
    (out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=protocol["gpu_uuid"],PATH=str(venv/"bin")+os.pathsep+os.environ.get("PATH",""))
    opener=build_opener(ProxyHandler({}))
    server=None
    def interrupted(*_):raise SystemExit("Assessment interrupted; release owned vLLM group")
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    try:
        with (out/"vllm.log").open("w") as log:
            server=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            (out/"server.json").write_text(json.dumps({"pid":server.pid,"pgid":server.pid,"started_unix":time.time()})+"\n")
            while True:
                if server.poll() is not None:raise RuntimeError("vLLM terminated during startup; inspect log")
                try:
                    with opener.open("http://127.0.0.1:18473/v1/models",timeout=5) as response:
                        models=json.load(response)
                    if "arex2-eval" not in {m["id"] for m in models["data"]}:raise ValueError("Unexpected model")
                    break
                except (OSError,ValueError):time.sleep(5)
            for arm,case,method in queue:
                path=root/arm/(case["case_id"]+".json")
                if sha(path)!=protocol["drafts_sha256"][str(path.relative_to(root))]:raise ValueError("Draft changed")
                row=json.loads(path.read_text());sources=json.loads((root/case["source_pack"]).read_text())
                if method=="grounding":
                    rubric=(root/"assessment-rubric.txt").read_text()
                    data={"question":row["query"],"obligations":case["obligations"],"draft":row["body"],"sources":sources}
                else:
                    rubric=(root/"reference-rubric.txt").read_text();original=gold[case["task_family"]]["original_reference"]
                    data={"original_question":original["body"],"reference_answers":{k:original[k] for k in ["ideal_answer","exact_answer","answers"] if k in original},"draft":row["body"]}
                prompt=rubric+"\nINPUT DATA:\n"+json.dumps(data,ensure_ascii=False)
                payload={"model":"arex2-eval","temperature":0,"max_tokens":6000,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":prompt}]}
                stem=out/(arm+"-"+case["case_id"]+"-"+method)
                Path(str(stem)+".request.json").write_text(json.dumps(payload,ensure_ascii=False)+"\n")
                start=time.monotonic();ann={"arm":arm,"case_id":case["case_id"],"method":method,"draft_sha256":sha(path),"assessor_model":"arex2-eval","independence":protocol["independence"]}
                try:
                    request=Request("http://127.0.0.1:18473/v1/chat/completions",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
                    with opener.open(request,timeout=1200) as response:raw_http=response.read()
                    Path(str(stem)+".http.json").write_bytes(raw_http)
                    packet=json.loads(raw_http);choice=packet["choices"][0];raw=choice["message"]["content"] or ""
                    Path(str(stem)+".response.txt").write_text(raw)
                    ann.update(usage=packet.get("usage"),finish_reason=choice["finish_reason"])
                    if choice["finish_reason"]!="stop":raise ValueError("Truncated response")
                    parsed=parse(raw)
                    if method=="grounding":
                        valid,invalid=validate_claims(parsed,row["body"],sources)
                        ann.update(status="partial_annotation" if invalid else "annotated_model_assisted",claims=valid,invalid_claims=invalid,
                            raw_claim_count=len(parsed["claims"]),usefulness=parsed.get("usefulness"),obligations=parsed.get("obligations"))
                    else:
                        if not isinstance(parsed.get("reference_units"),list):raise ValueError("Missing reference units")
                        ann.update(status="annotated_reference_alignment",**parsed)
                except Exception as error:ann.update(status="annotation_invalid_or_failed",error_type=type(error).__name__,error=str(error))
                ann["latency_seconds"]=time.monotonic()-start
                Path(str(stem)+".json").write_text(json.dumps(ann,ensure_ascii=False,indent=2)+"\n")
                print(json.dumps({k:ann.get(k) for k in ["arm","case_id","method","status","latency_seconds"]}),flush=True)
    finally:
        if server is not None:
            try:os.killpg(server.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid,signal.SIGKILL);server.wait()
        after=subprocess.check_output(gpu_command,text=True)
        (out/"gpu-after.csv").write_text(after)
        remaining={int(line.split(",",1)[0]) for line in after.splitlines() if line}
        (out/"terminal.json").write_text(json.dumps({"server_exit_code":server.returncode if server else None,"ended_unix":time.time(),
            "previous_gpu_pids_still_listed":sorted(previous_pids&remaining),"previous_gpu_pids_no_longer_listed":sorted(previous_pids-remaining)},indent=2)+"\n")


if __name__=="__main__":
    main()
