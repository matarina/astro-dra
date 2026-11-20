"""Literal quote provenance diagnostics; no semantic verdict or report changes."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,action='append',required=True)
    ap.add_argument('--out-dir',type=Path,required=True);a=ap.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    rows=[];hashes={}
    for attempt in a.attempt:
        paths=[attempt/'plan.json',attempt/'calls.json'];plan=json.loads(paths[0].read_text());calls=json.loads(paths[1].read_text())
        jobs={j['name']:j for j in plan['jobs']}
        for call in calls:
            job=jobs[call['name']];path=attempt/call['name']/'material.txt';paths.append(path);material=path.read_text()
            for issue in call.get('issues',[])+call.get('checked',[]):
                claim=job['claims'].get(str(issue.get('claim_id')),{})
                for atom in issue.get('atom_checks',[]):
                    quote=atom.get('evidence_quote')
                    if not isinstance(quote,str) or not quote:continue
                    rows.append(dict(attempt=str(attempt),name=call['name'],arm=call['arm'],claim_id=issue.get('claim_id'),
                        attribute=atom.get('attribute'),claim_value=atom.get('claim_value'),source_value=atom.get('source_value'),
                        result=atom.get('result'),evidence_quote=quote,literal_in_supplied_material=quote in material,
                        literal_in_parent_report=quote in claim.get('text',''),
                        assertion_span_id=atom.get('assertion_span_id'),atom_evidence_source_id=atom.get('evidence_source_id')))
        for p in paths:hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(scope='Evaluation-only exact quote origin and model attribute coverage diagnostic',rows=rows,input_hashes=hashes,
        quality_claim=None,newly_credited_corrections=0,
        limits=['Literal absence alone cannot adjudicate the scientific claim or a legitimate paraphrase.',
                'A not_reported label may be appropriate for an abstract even when the full paper contains the method.',
                'A quote copied only from the report is not independent source evidence.',
                'No proposed revision was applied or independently adjudicated.'])
    (a.out_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'diagnostic-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(atom_quotes=len(rows),report_only_quotes=sum(r['literal_in_parent_report'] and not r['literal_in_supplied_material'] for r in rows))))


if __name__=='__main__':main()
