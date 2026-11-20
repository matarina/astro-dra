"""Exact offline replay of source-only reading and attribute-comparison diagnostic."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from research_verify.source_fact_ledger import ledger_prompt,parse_ledger,attribute_comparison_prompt,parse_attribute_comparisons,parse_ledger_partial


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    plan=json.loads((a.attempt/'plan.json').read_text());complete=json.loads((a.attempt/'completion.json').read_text());calls=json.loads((a.attempt/'calls.json').read_text());data=json.loads(Path(plan['inputs']).read_text());prior=json.loads((Path(plan['extraction_attempt'])/'completion.json').read_text());extracted={r['case_id']:r['extraction']for r in prior['results']};cursor=0
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text());container=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
    assert container['State']['Status']=='exited'and container['State']['ExitCode']==0 and container['Image']==handle['image']
    assert next(m for m in container['Mounts']if m['Destination']=='/workspace')['RW']is False
    for fn in [a.attempt/'prestart-freeze.json',a.attempt.parent/'launch-code-freeze.json']:
        for path,digest in json.loads(fn.read_text()).items():
            actual=Path(path)
            if actual.is_relative_to('/workspace'):actual=Path.cwd()/actual.relative_to('/workspace')
            assert sha(actual)==digest
    def invoke(prompt,stage):
        nonlocal cursor
        i=cursor;cursor+=1;c=calls[i];pp=a.attempt/f'call-{i:02d}-prompt.txt';rp=a.attempt/f'call-{i:02d}-response.txt'
        assert c['stage']==stage and prompt==pp.read_text()and sha(pp)==c['prompt_sha256']and len(prompt)==c['prompt_chars']and len(prompt)<=70000
        assert c['status']=='returned'and sha(rp)==c['response_sha256']
        if c.get('origin')=='strict_cache':
            old=Path(c['cached_from']);assert sha(old)==c['response_sha256']and old.with_name('call-00-prompt.txt').read_text()==prompt and i==0
        return rp.read_text()
    results=[];summary=[]
    replay_failure=None
    try:
        for case in data['cases']:
            report=Path(case['report_path']).read_text();assert sha(Path(case['report_path']))==case['report_sha256']
            for u in extracted[case['case_id']]:
                for claim in u['claims']:assert report[claim['report_start']:claim['report_end']]==claim['quote']
            ledger=(parse_ledger_partial if plan.get('partial_ledger')else parse_ledger)(invoke(ledger_prompt(case['query'],case['source_units']),case['case_id']+':source_ledger'),case['source_units'])
            batches=[];results.append(dict(case_id=case['case_id'],ledger=ledger,batches=batches));claims=[dict(report_unit_id=x['report_unit_id'],claims=[c])for x in extracted[case['case_id']]for c in x['claims']]
            for i,start in enumerate(range(0,len(claims),12)):
                b=claims[start:start+12];raw=invoke(attribute_comparison_prompt(case['query'],b,ledger,case['source_units']),case['case_id']+':attribute_comparison:'+str(i));batches.append(parse_attribute_comparisons(raw,b,case['source_units']))
            comparisons=[c for b in batches for c in b['comparisons']]
            summary.append(dict(case_id=case['case_id'],ledger_facts=len(ledger['facts']),unbound_facts=len(ledger['unbound_facts']),comparisons=len(comparisons),unassessed=sum(c['relation']is None for c in comparisons)))
    except ValueError as exc:
        replay_failure=str(exc)
        assert complete['status']=='unavailable'and complete['failure']['error_type']=='ValueError'
    assert (complete['status']=='completed')==(replay_failure is None)and complete['results']==results and complete['frozen_inputs_unchanged']and cursor==len(calls)==complete['calls']and cursor<=8
    audit=dict(scope='Parser/provenance replay, not independent scientific assessment',exit_code=0,workflow_status=complete['status'],failure_replayed=replay_failure,launch_start_end_hashes_match=True,exact_prompts_replies_replayed=True,calls=cursor,fresh_calls=sum(c.get('origin','fresh')=='fresh'for c in calls),cached_calls=sum(c.get('origin')=='strict_cache'for c in calls),cases=summary,report_modifications=0,quality_claim=None,newly_credited_corrections=0)
    a.out_dir.mkdir(exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':main()
