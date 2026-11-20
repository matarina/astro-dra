"""Exact per-source quote exposure in private sequential traces; never truth scores."""
import argparse,hashlib,json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    records=[json.loads(line)for line in a.trace.read_text().splitlines()];views={};observations=[]
    for record in records:
        data=record['data'];key=(data.get('group'),data.get('round',1))
        if record['stage']=='sequential_group_input':
            assert all(not v.get('block')or v['block']in data['material']for v in data['material_views'].values())
            views[key]=data['material_views']
        if record['stage']!='sequential_group_review':continue
        supplied=views[key]
        for kind in ['issues','checked']:
            for item in data[kind]:
                quotes=[dict(source_id=e.get('source_id'),quote=e.get('quote'),origin='evidence_sources')
                        for e in item.get('evidence_sources',[])if isinstance(e,dict)]
                for atom in item.get('atom_checks',[]):
                    if isinstance(atom,dict):quotes.append(dict(source_id=atom.get('source_id',item.get('source_id')),
                        quote=atom.get('evidence_quote'),origin='atom_check',attribute=atom.get('attribute'),model_result=atom.get('result')))
                for q in quotes:
                    text=q['quote'];sid=str(q['source_id']);own=supplied.get(sid,{})
                    if not isinstance(text,str)or not text.strip():
                        found=dict(exposure='no_literal_quote_supplied',own_text=False,own_metadata=False,own_rendered_block=False,other_source_ids=[])
                    else:
                        in_text=text in own.get('text','');in_metadata=text in own.get('metadata','');in_block=text in own.get('block','')
                        others=[int(k)for k,v in supplied.items()if k!=sid and (text in v.get('text','')or text in v.get('metadata','')or text in v.get('block',''))]
                        found=dict(exposure='located'if in_text or in_metadata or in_block else 'not_located_in_cited_view',
                            own_text=in_text,own_metadata=in_metadata,own_rendered_block=in_block,other_source_ids=others)
                    observations.append(dict(group=key[0],round=key[1],kind=kind,claim_id=item.get('claim_id'),model_status=item.get('status'),**q,**found))
    a.out_dir.mkdir(parents=True,exist_ok=False)
    result=dict(scope='Exact quotation locatability in actual supplied per-source registry; NOT truth, entailment or independent adjudication',
        trace_sha256=hashlib.sha256(a.trace.read_bytes()).hexdigest(),source_views=len(views),observations=observations,
        limits=['Whitespace/paraphrase/ellipsis differences remain unlocated; no fuzzy recovery','Matching text elsewhere does not silently reassign source','An absent quote does not prove a claim false; a located quote does not establish support','Counts are quotation receipts, not semantic coverage or correction scores'],quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(groups_and_rounds=len(views),quotation_receipts=len(observations))))


if __name__=='__main__':main()
