"""Reuse frozen backend installation checks, then run retrieval without a model."""
import os
from pathlib import Path

path=Path("/workspace/scripts/benchmark_report_boot.py")
code=path.read_text()
old='runpy.run_path("/workspace/scripts/run_intent_pilot.py", run_name="__main__")'
if code.count(old)!=1:
    raise ValueError("Unexpected common bootstrap")
code=code.replace(old,'runpy.run_path("/workspace/scripts/run_benchmark_retrieval.py", run_name="__main__")')
os.environ["PILOT_CASE_ID"]="retrieval-installed-code"
exec(compile(code,str(path),"exec"),{"__name__":"__main__"})
