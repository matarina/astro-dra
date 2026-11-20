"""Offline exact frozen-prompt comparison audit, not independent quality scoring."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from research_verify.source_fact_ledger import parse_attribute_comparisons
from research_verify.comparison_accounting import attribute_label_accounting


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    complete=json.loads((a.attempt/'completion.json').read_text());plan=json.loads((a.attempt/'plan.json').read_text());calls=json.loads((a.attempt/'calls.json').read_text());handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    container=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
    assert container['State']['Status']=='exited'and container['State']['ExitCode']==0 and container['Image']==handle['image']
    assert next(m for m in container['Mounts']if m['Destination']=='/workspace')['RW']is False
    for fn in [a.attempt/'prestart-freeze.json',a.attempt.parent/'launch-code-freeze.json']:
        for path,digest in json.loads(fn.read_text()).items():
            actual=Path(path)
            if actual.is_relative_to('/workspace'):actual=Path.cwd()/actual.relative_to('/workspace')
            assert sha(actual)==digest
    assert len(calls)==complete['calls']==4 and complete['frozen_inputs_unchanged']
    summary=[]
    for job in plan['jobs']:
        pair=[c for c in calls if c['case_id']==job['case_id']];assert len(pair)==2 and {c['model']for c in pair}==set(plan['models'])
        assert len({c['prompt_sha256']for c in pair})==1
        for c in pair:
            i=c['index'];pp=a.attempt/f'call-{i:02d}-prompt.txt';rp=a.attempt/f'call-{i:02d}-response.txt';r=complete['results'][i]
            assert pp.read_text()==job['prompt']and sha(pp)==c['prompt_sha256']and len(job['prompt'])==c['prompt_chars']
            assert r['case_id']==job['case_id']and r['model']==c['model']
            if c.get('origin')=='strict_cache':assert sha(Path(c['cached_from']))==c['response_sha256']and c['model']=='deepseek-v4-flash'
            if c['status']=='returned':
                assert sha(rp)==c['response_sha256']
                if r['status']=='parsed':
                    parsed=parse_attribute_comparisons(rp.read_text(),job['extracted'],job['units']);assert parsed==r['parsed']
                    assert [attribute_label_accounting(x)for x in parsed['comparisons']]==r['accounting']
                else:assert r['status']=='unavailable'
            else:assert r['status']=='unavailable'and c['error_type']==r['error_type']
            summary.append(dict(case_id=c['case_id'],model=c['model'],origin=c.get('origin'),status=r['status'],finish_reason=c.get('response_metadata',{}).get('finish_reason'),parsed_claims=len(r.get('parsed',{}).get('comparisons',[])),usable_comparisons=sum(x.get('relation')is not None for x in r.get('parsed',{}).get('comparisons',[])),unassessed_comparisons=sum(x.get('relation')is None for x in r.get('parsed',{}).get('comparisons',[])),internally_inconsistent=sum(bool(x['internal_flags'])for x in r.get('accounting',[]))))
    assert sum(c.get('origin')=='fresh'for c in calls)==complete['fresh_calls']<=plan['maximum_fresh_calls']
    assert sum(c.get('origin')=='strict_cache'for c in calls)==complete['cached_calls']==(0 if plan.get('reference_ledger')else 2)
    audit=dict(scope='Exact original-prompt/cache/parser/provenance comparison, not scientific assessment or production model switch',exit_code=0,launch_start_end_hashes_match=True,byte_identical_prompts_per_pair=True,calls=4,fresh_calls=complete['fresh_calls'],cached_calls=complete['cached_calls'],rows=summary,report_modifications=0,quality_claim=None,newly_credited_corrections=0)
    a.out_dir.mkdir(exist_ok=False);(a.out_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':main()
