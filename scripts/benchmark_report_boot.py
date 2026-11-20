"""Verify and install a frozen arm in a disposable report-evaluation container."""
import hashlib
import ast
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


root = Path("/experiment")
arm = os.environ["PILOT_ARM"]
if arm not in {"baseline", "candidate"}:
    raise ValueError("Unknown arm")
freeze = json.loads((root/"freeze.json").read_text())
for name, expected in freeze["sha256"].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
        raise ValueError("Frozen input/runner changed: "+name)
manifest = json.loads((root/(arm+"-code-hashes.json")).read_text())
code = root/(arm+"-code")
for name, expected in manifest.items():
    if hashlib.sha256((code/name).read_bytes()).hexdigest() != expected:
        raise ValueError("Frozen code changed: "+name)
subprocess.run([sys.executable, str(code/"deployment/install_overlays.py"), "--source",
    str(code/"local_deep_research"), "--manifest", str(root/(arm+"-install-manifest.json"))],
    check=True, stdout=subprocess.DEVNULL)
app = Path(importlib.import_module("local_deep_research").__file__).parent
rv = Path(importlib.import_module("research_verify").__file__).parent
overlay = json.loads((code/"deployment/overlay-manifest.json").read_text())
installer_ast = ast.parse((code/"deployment/install_overlays.py").read_text())
collection_hook = next(ast.literal_eval(node.value) for node in installer_ast.body
    if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=="COLLECTION_HOOK" for t in node.targets))
installed = {}
for name, expected in manifest.items():
    relative = Path(name).relative_to("local_deep_research") if name.startswith("local_deep_research/") else None
    if relative is None or relative.suffix != ".py":
        continue
    if relative.parts[0] == "research_verify":
        path = rv/Path(*relative.parts[1:])
    elif str(relative) in overlay:
        path = app/overlay[str(relative)]
    else:
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if str(relative)=="langgraph_agent_strategy.py" and (code/"local_deep_research/research_verify/source_collection.py").exists():
        original=(code/name).read_text()
        expected=hashlib.sha256((original if "# Source collection feedback and stable-identifier deduplication." in original
            else original+collection_hook).encode()).hexdigest()
    if actual != expected:
        raise ValueError("Installed code differs: "+name)
    installed[name] = actual
out = root/arm
out.mkdir(exist_ok=True)
(out/(os.environ["PILOT_CASE_ID"]+".installed.json")).write_text(json.dumps(installed,indent=2)+"\n")
# The generation runner never opens reference-gold.json.
runpy.run_path("/workspace/scripts/run_intent_pilot.py", run_name="__main__")
