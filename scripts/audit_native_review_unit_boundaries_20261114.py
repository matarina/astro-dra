"""Replay frozen/native review unit boundaries; verify coordinates and coverage."""
import argparse
import ast
from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path

from research_verify.claims import extract_report_claims
from research_verify.evidence_flow import review_units


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113')
    old=base/'native-original-xenium-pair-20261114-v1/attempt/code/local_deep_research/research_verify/evidence_flow.py'
    freeze=json.loads((base/'native-original-xenium-pair-20261114-v1/launch-code-freeze.json').read_text())
    assert sha(old)==freeze['local_deep_research/research_verify/evidence_flow.py']
    tree=ast.parse(old.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='review_units')
    scope=dict(re=re,replace=replace,extract_report_claims=extract_report_claims)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(old),'exec'),scope)
    inputs=base/'report-coordinate-repair-audit-20261114-v1/audit.json';rows=[]
    for entry in json.loads(inputs.read_text())['reports']:
        path=Path(entry['path']);raw=path.read_text()
        text=json.loads(raw)['body'] if entry['scope']=='six_request_rerun' else raw
        assert hashlib.sha256(text.encode()).hexdigest()==entry['report_sha256']
        before=scope['review_units'](text);after=review_units(text)
        assert all(text[c.report_start:c.report_end]==c.text for c in before+after)
        covered=lambda units:{i for c in units for i in range(c.report_start,c.report_end) if text[i].isalnum()}
        missing=covered(before)-covered(after)
        rows.append(dict(path=str(path),file_sha256=sha(path),scope=entry['scope'],before_units=len(before),after_units=len(after),
            lost_alphanumeric_positions=len(missing),lost_examples=[dict(position=i,context=text[max(0,i-30):i+40]) for i in sorted(missing)[:8]],
            exact_raw_coordinates=True,before_max_unit_chars=max(map(lambda c:len(c.text),before),default=0),
            after_max_unit_chars=max(map(lambda c:len(c.text),after),default=0)))
    (a.out_dir/'audit.json').write_text(json.dumps(dict(scope='Syntax/input coverage only, not source association truth or quality gain',
        before_code_path=str(old),before_sha256=sha(old),after_sha256=sha(Path('local_deep_research/research_verify/evidence_flow.py')),
        reports=rows,quality_claim=None),ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(rows,ensure_ascii=False))
    assert not any(r['lost_alphanumeric_positions'] for r in rows),'Inspect lost original review content'


if __name__=='__main__':main()
