"""Offline per-row binding diagnosis. Does not alter frozen protocol outcomes."""
import argparse,json,hashlib
from pathlib import Path
from research_verify.literal_occurrences import parse_comparison
from research_verify.request_additions import _json


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    data=json.loads(a.inputs.read_text());cases={c['case_id']:c for c in data['cases']};complete=json.loads((a.attempt/'completion.json').read_text());results={r['case_id']:r for r in complete['results']};rows=[]
    for call in json.loads((a.attempt/'calls.json').read_text()):
        if ':compare:'not in call['stage']:continue
        name=call['stage'].split(':')[0];raw=a.attempt/f"call-{call['index']:02d}-response.txt"
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==call['response_sha256']
        for item in _json(raw.read_text())['comparisons']:
            selected=[dict(report_unit_id=u['report_unit_id'],claims=[c])for u in results[name]['extraction']for c in u['claims']if c['claim_id']==item.get('claim_id')]
            try:
                assert len(selected)==1
                bound=parse_comparison(json.dumps({'comparisons':[item]}),selected,cases[name]['source_units'])[0]
                row=dict(case_id=name,call=call['index'],claim_id=item['claim_id'],binding_status='located_not_semantically_validated',raw_relation=item['relation'],report_quote=selected[0]['claims'][0]['quote'],model_assertion=selected[0]['claims'][0]['assertion'],bound_comparison=bound)
            except(ValueError,AssertionError,KeyError,TypeError)as exc:
                row=dict(case_id=name,call=call['index'],claim_id=item.get('claim_id'),binding_status='unavailable',reason=str(exc),raw_relation_not_accepted=item.get('relation'))
            rows.append(row)
    receipt=dict(scope='Per-row diagnostic of saved replies; does not supersede frozen batch-parser outcomes, repair quotes, edit reports, or adjudicate scientific truth',rows=rows,newly_credited_corrections=0)
    a.out_dir.mkdir(exist_ok=False);(a.out_dir/'per-row-binding.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    for name in cases:
        subset=[r for r in rows if r['case_id']==name];print(name,'located',sum(r['binding_status']=='located_not_semantically_validated'for r in subset),'unavailable',sum(r['binding_status']=='unavailable'for r in subset))
    for r in rows:
        if r['binding_status']=='unavailable':print(r['case_id'],r['claim_id'],r['reason'])


if __name__=='__main__':main()
