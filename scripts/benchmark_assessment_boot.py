"""Install the frozen candidate only for disposable assisted assessment."""
from pathlib import Path
import runpy
import subprocess
import sys

root=Path("/experiment")
code=root/"candidate-code"
subprocess.run([sys.executable,str(code/"deployment/install_overlays.py"),"--source",
    str(code/"local_deep_research"),"--manifest",str(root/"candidate-install-manifest.json")],
    check=True,stdout=subprocess.DEVNULL)
runpy.run_path("/workspace/scripts/assess_benchmark_reports.py",run_name="__main__")
