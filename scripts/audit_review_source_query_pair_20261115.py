"""Exact native check/material/parser/application replay; no scientific scoring."""
import argparse,copy,hashlib,json,subprocess
from pathlib import Path
from research_verify.evidence_flow import review_answer
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prior-attempt',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    att=a.run/'attempt';h=json.loads((a.run/'execution-handle.json').read_text());c=json.loads(subprocess.check_output(['docker','inspect',h['container_id']]))[0];assert c['State']['ExitCode']==0 and not c['State']['Running']and c['Image']==h['image'];assert not next(m for m in c['Mounts']if m['Destination']=='/workspace')['RW']
    for f in [a.run/'launch-code-freeze.json',att/'prestart-freeze.json']:
        for k,v in json.loads(f.read_text()).items():assert sha(Path(k.removeprefix('/workspace/')))==v,k
    plan=json.loads((att/'plan.json').read_text());prior_result=json.loads((a.prior_attempt/'inherited/result.json').read_text());report=(a.prior_attempt/'inherited/report.txt').read_text();calls=json.loads((att/'calls.json').read_text());cursor=0;rows=[]
    for call in calls:
        assert sha(att/f"call-{call['index']:02d}-prompt.txt")==call['prompt_sha256']
        assert call['status']=='returned'and sha(att/f"call-{call['index']:02d}-response.txt")==call['response_sha256']
        if call['origin']=='strict_cache':
            rp=Path(call['cached_from']);assert sha(rp)==call['response_sha256']
    for arm in plan['arms']:
        sources=copy.deepcopy(prior_result['sources']);fetch=FixedSources();folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
        class Handler:
            settings_snapshot=plan['settings']|{'citation.review_source_scoped_queries':arm=='retrieval','citation.review_compound_terms':arm=='retrieval'}
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _invoke_text(self,prompt,trace=None,stage='model'):
                nonlocal cursor
                call=calls[cursor];cursor+=1;assert call['arm']==arm and call['stage']==stage
                assert prompt==(att/f"call-{call['index']:02d}-prompt.txt").read_text(),(arm,stage,call['index'])
                return (att/f"call-{call['index']:02d}-response.txt").read_text()
        revised,docs,applied,unresolved,shown=review_answer(Handler(),plan['query'],report,native_documents(sources),sources,trace,None,1,200000,dict(fetcher=fetch),dict(remaining=6));actual=json.loads((att/arm/'result.json').read_text())
        assert actual['status']=='completed'and revised==(att/arm/'report.txt').read_text();assert applied==actual['applied']and unresolved==actual['unresolved']and sorted(shown)==actual['shown_source_ids'];assert sources==actual['sources']and fetch.events==actual['supplement_requests']
        rows.append(dict(arm=arm,report_sha256=sha(att/arm/'report.txt'),report_chars=len(revised),report_changed=revised!=report,applied_count=len(applied),unresolved_records=len(unresolved)))
    assert cursor==len(calls)
    result=dict(scope='Exact provenance and native-stage replay only; not independent scientific adjudication',container_id=c['Id'],image=c['Image'],exit_code=0,read_only_workspace=True,launch_start_completion_hashes_match=True,all_prompt_reply_hashes_verified=True,all_materials_prompts_parsers_application_outputs_and_cache_reproduced=True,arms=rows,logical_calls=len(calls),fresh_model_calls=sum(c['origin']=='fresh_model'for c in calls),strict_cached_calls=sum(c['origin']=='strict_cache'for c in calls),network_retrieval_reads=0,new_independently_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
