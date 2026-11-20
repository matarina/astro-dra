"""Offline prompt transport audit: no model replay verdict or quality score."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from research_verify.evidence_flow import confirm_repairs
from research_verify.generation import SourceMaterial


def digest(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    rows=[json.loads(line) for line in (a.attempt/'candidate/trace.jsonl').read_text().splitlines()]
    group=next(row['data'] for row in rows if row['stage']=='sequential_group_input' and row['data']['group']==3)
    # Preserve the actual structured view, not a lossy delimiter reparse.
    material=SourceMaterial(group['material'],{int(k):v for k,v in group['material_views'].items()})
    proposals=next(row['data']['issues'] for row in rows if row['stage']=='sequential_group_proposals' and row['data']['group']==3)
    old_path=a.attempt/'candidate/call-016-prompt.txt';old=old_path.read_text();prompts=[]
    handler=SimpleNamespace(get_setting=lambda k,d=None:True if k in {'citation.attribute_confirmation_review','citation.confirmation_consistency_review'} else d,
        _invoke_text=lambda prompt,**kw:prompts.append(prompt) or '{"decisions":[]}')
    baseline=(a.attempt/'baseline/report.txt').read_text();plan=json.loads((a.attempt/'plan.json').read_text())
    report,applied,pending=confirm_repairs(handler,baseline,proposals,material,plan['query'],SimpleNamespace(record=lambda *args:None))
    assert report==baseline and not applied and pending and len(prompts)==1
    new=prompts[0];decoder=json.JSONDecoder();prefix='\nCandidates:\n'
    old_before,old_after=old.split(prefix,1);new_before,new_after=new.split(prefix,1)
    old_candidates,old_end=decoder.raw_decode(old_after);new_candidates,new_end=decoder.raw_decode(new_after)
    assert old_before==new_before and old_after[old_end:]==new_after[new_end:]
    changes=[]
    for original,current in zip(old_candidates,new_candidates,strict=True):
        old_contexts=original.pop('source_contexts');new_contexts=current.pop('source_contexts')
        assert original==current
        old_ids=[x['source_id'] for x in old_contexts];new_ids=[x['source_id'] for x in new_contexts]
        assert all(x in new_contexts for x in old_contexts)
        changes.append(dict(original_statement=original['original'],before_source_ids=old_ids,after_source_ids=new_ids,
                            added_contexts=[x for x in new_contexts if x not in old_contexts]))
    assert changes[0]['before_source_ids']==changes[0]['after_source_ids']==[13]
    assert changes[1]['before_source_ids']==[14] and changes[1]['after_source_ids']==[14,15]
    # Duplicate source identities do not turn abstracts into full paper evidence.
    assert len(changes[1]['added_contexts'])==1 and changes[1]['added_contexts'][0]['context']
    a.out_dir.mkdir(parents=True,exist_ok=False)
    (a.out_dir/'expanded-confirmation-prompt.txt').write_text(new)
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    code=Path('local_deep_research/research_verify/evidence_flow.py')
    (a.out_dir/'evidence_flow.py').write_bytes(code.read_bytes())
    audit=dict(scope='Offline confirmation-context transport only; no new or cached semantic verdict evaluated',
        old_prompt_sha256=digest(old_path.read_bytes()),new_prompt_sha256=digest(new.encode()),code_sha256=digest(code.read_bytes()),
        identical_except_source_contexts=True,changes=changes,model_calls=0,report_unchanged=True,
        quality_claim=None,newly_credited_corrections=0,
        limits=['Supplying duplicate abstracts does not resolve absent method evidence','No independent outcome adjudication'])
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(changes=[dict(before=x['before_source_ids'],after=x['after_source_ids']) for x in changes],model_calls=0)))


if __name__=='__main__':main()
