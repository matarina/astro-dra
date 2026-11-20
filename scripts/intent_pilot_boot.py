"""Install one frozen experiment arm in a disposable container only."""
import os
from pathlib import Path
import runpy
import subprocess

arm = os.environ["PILOT_ARM"]
if arm not in {"baseline", "candidate"}:
    raise ValueError("Unknown arm")
source = Path("/experiment") / (arm + "-code")
subprocess.run(["/install/.venv/bin/python", str(source / "deployment/install_overlays.py"),
                "--source", str(source / "local_deep_research"), "--manifest",
                str(source / "deployment/overlay-manifest.json")], check=True, stdout=subprocess.DEVNULL)
runpy.run_path("/workspace/scripts/run_intent_pilot.py", run_name="__main__")
