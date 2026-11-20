"""Load frozen inference code for offline blinded assessment only."""
from pathlib import Path
import runpy
import subprocess
import sys

source = Path("/experiment/candidate-code")
subprocess.run([sys.executable,str(source / "deployment/install_overlays.py"),
                "--source",str(source / "local_deep_research"),"--manifest",
                str(source / "deployment/overlay-manifest.json")],check=True,stdout=subprocess.DEVNULL)
runpy.run_path("/workspace/scripts/assess_intent_pilot.py",run_name="__main__")
