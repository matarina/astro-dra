"""Install frozen arm in disposable container; never touch running instances."""
from pathlib import Path
import subprocess
import sys

arm = sys.argv[1]
if arm not in {"baseline", "candidate"}:
    raise ValueError("Unknown arm")
code = Path("/experiment")/(arm+"-code")
subprocess.run([sys.executable, str(code/"deployment/install_overlays.py"), "--source",
                str(code/"local_deep_research"), "--manifest", str(code/"deployment/overlay-manifest.json")],
               check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, "/workspace/run_metadata_unknowns.py", "/experiment", arm], check=True)
