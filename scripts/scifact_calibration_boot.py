"""Install frozen code inside an ephemeral calibration container only."""
from pathlib import Path
import runpy
import subprocess
import sys

code = Path("/experiment/code")
subprocess.run([sys.executable,str(code/"deployment/install_overlays.py"),
                "--source",str(code/"local_deep_research"),"--manifest",
                str(code/"deployment/overlay-manifest.json")],check=True,stdout=subprocess.DEVNULL)
runpy.run_path("/workspace/run_scifact_calibration.py",run_name="__main__")
