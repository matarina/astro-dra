"""Replay actual native proposal eligibility, not source-truth adjudication."""
import argparse
import json
from pathlib import Path
import hashlib

from research_verify.evidence_flow import apply_review, parse_review, _review_material, required_sources, document_structure_spans
from scripts.prepare_source_detail_material_20261114 import native_documents


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True);a=ap.parse_args()
    completion=json.loads((a.attempt/'completion.json').read_text());assert completion['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());original=(a.attempt/'original-report.txt').read_text()
    freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    manifest_name=next(name for name in freeze if name.endswith('/case-manifest.json'))
    manifest_path=Path.cwd()/Path(manifest_name).relative_to('/workspace') if manifest_name.startswith('/workspace/') else Path(manifest_name)
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==freeze[manifest_name]
    case=json.loads(manifest_path.read_text())['cases'][0];source_path=Path(case['source'])
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==plan['source_pack_sha256']
    sources=json.loads(source_path.read_text());docs=native_documents(sources)
    reserve=min(8000,len(json.dumps(document_structure_spans(original),ensure_ascii=False)))
    a.out_dir.mkdir(parents=True,exist_ok=False);rows=[]
    for arm in plan['arms']:
        folder=a.attempt/arm
        events=[json.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
        requests=[e['data'] for e in events if e['stage']=='native_check_request']
        calls=[c for c in json.loads((folder/'calls.json').read_text()) if c['stage']=='native_check']
        assert len(requests)==len(calls)
        groups=plan.get('baseline_groups',plan['groups']) if arm=='baseline' else plan['groups']
        for request,call in zip(requests,calls):
            row=dict(arm=arm,group=request['review_group'],call_id=call['call_id'])
            if call['status']!='returned':rows.append({**row,'status':'model_unavailable'});continue
            raw=(folder/f"call-{call['call_id']:03d}-response.txt").read_text()
            claims={int(k):v for k,v in groups[request['review_group']-1].items()}
            try:issues,checked=parse_review(raw,claims,include_checked=True)
            except Exception as exc:rows.append({**row,'status':'parse_unavailable','error_type':type(exc).__name__});continue
            assert request['round']==1,'Supplemented source state needs a separate replay'
            text='\n'.join(c['text'] for c in claims.values())
            material,_=_review_material(docs,plan['query']+'\n'+text,claims,required_sources(text,sources),max(2000,60000-reserve))
            prompt_material=request['prompt'].split('\nSUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
            assert str(material)==prompt_material,'Reconstructed source view differs from actual request'
            for issue in issues:
                if issue.get('status') not in {'contradiction','scope_correction','version_update'}:continue
                _,eligible,pending=apply_review(original,[issue],material)
                rows.append(dict(**row,status='proposed_issue',claim_id=issue.get('claim_id'),issue_status=issue['status'],
                    has_nonempty_replacement=isinstance(issue.get('replacement'),str) and bool(issue['replacement'].strip()),
                    eligible_for_semantic_confirmation=bool(eligible),source_id=issue.get('source_id'),
                    statement=issue.get('statement'),replacement=issue.get('replacement'),
                    evidence_sources=issue.get('evidence_sources'),evidence_quote=issue.get('evidence_quote'),
                    unresolved_after_eligibility=pending))
    result=dict(scope='Native parse and quote/location eligibility replay only; not support, correction or retention verdict',
                rows=rows,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(rows=len(rows),eligible=sum(bool(r.get('eligible_for_semantic_confirmation')) for r in rows),
                         missing_replacement=sum(r.get('status')=='proposed_issue' and not r['has_nonempty_replacement'] for r in rows))))


if __name__=='__main__':main()
