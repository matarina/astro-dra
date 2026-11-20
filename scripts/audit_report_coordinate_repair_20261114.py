"""Offline before/after input exposure audit; never a semantic correction score."""
import argparse
import hashlib
import json
import sys
import types
from pathlib import Path

from research_verify import report_syntax
from research_verify.claims import extract_report_claims


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before-module',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=False)
    old=types.ModuleType('coordinate_audit_before');sys.modules[old.__name__]=old
    exec(compile(args.before_module.read_text(),str(args.before_module),'exec'),old.__dict__)
    new_layout=report_syntax.layout
    inputs=[(p,'original_archive_text',p.read_text()) for p in sorted(Path(
        'evaluation/pane2-independent-review-20261113/nonimmune-sources/archive-reports').rglob('*.txt'))]
    readiness=json.loads(Path('evaluation/frontier-strategy-20261113/six-task-input-readiness-20261114-v1.json').read_text())
    for row in readiness['tasks']:
        p=Path(row['report_path']);inputs.append((p,'six_request_rerun',json.loads(p.read_text())['body']))
    results=[]
    for path,scope,report in inputs:
        try:
            report_syntax.layout=old.layout;before=extract_report_claims(report)
        finally:report_syntax.layout=new_layout
        after=extract_report_claims(report)
        def cited_spans(claims):
            return {(c.report_start,c.report_end,tuple(c.citations)) for c in claims if c.citations}
        a,b=cited_spans(before),cited_spans(after)
        results.append(dict(path=str(path),scope=scope,file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            report_sha256=hashlib.sha256(report.encode()).hexdigest(),chars=len(report),
            non_commonmark_separators={repr(c):report.count(c) for c in '\f\v\x85\u2028\u2029'},
            before_cited_units=len(a),after_cited_units=len(b),
            added_or_relocated_cited_units=len(b-a),removed_or_relocated_cited_units=len(a-b),
            unchanged_cited_units=len(a&b)))
    (args.out_dir/'audit.json').write_text(json.dumps(dict(
        scope='Report parsing/extraction input coverage only; no support, identity truth or correction score',
        before_module=str(args.before_module),before_sha256=hashlib.sha256(args.before_module.read_bytes()).hexdigest(),
        after_sha256=hashlib.sha256(Path(report_syntax.__file__).read_bytes()).hexdigest(),
        reports=results,quality_claim=None),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
