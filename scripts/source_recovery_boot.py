"""Install one frozen arm into a disposable offline probe container."""
from pathlib import Path
import subprocess
import sys

arm = sys.argv[1]
if arm not in {"baseline", "candidate"}:
    raise ValueError("Unknown arm")
root = Path("/experiment")
code = root/(arm+"-code")
subprocess.run([sys.executable, str(code/"deployment/install_overlays.py"), "--source",
    str(code/"local_deep_research"), "--manifest", str(code/"deployment/overlay-manifest.json")],
    check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, "/workspace/probe_source_recovery.py", str(root), arm], check=True)
