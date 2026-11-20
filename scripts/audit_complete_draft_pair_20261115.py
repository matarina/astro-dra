"""Exact offline native synthesis replay of the complete draft pair."""
import argparse,copy,hashlib,json,subprocess
from datetime import datetime
from pathlib import Path
from research_verify import evidence_flow
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    r=Path.cwd();att=a.run/'attempt';handle=json.loads((a.run/'execution-handle.json').read_text());c=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
    assert not c['State']['Running']and c['State']['ExitCode']==0 and c['Image']==handle['image'];assert not next(x for x in c['Mounts']if x['Destination']=='/workspace')['RW']
    for fp in [a.run/'launch-code-freeze.json',att/'prestart-freeze.json']:
        for key,value in json.loads(fp.read_text()).items():assert sha(r/key.removeprefix('/workspace/'))==value,key
    case=_manifest_cases(a.case_manifest)[0];original=case['draft'].read_text();sources=json.loads(case['source'].read_text());plan=json.loads((att/'plan.json').read_text());completion=json.loads((att/'completion.json').read_text());calls=json.loads((att/'calls.json').read_text());clock=datetime.fromisoformat(plan['fixed_writer_clock'])
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock
    for row in calls:
        assert sha(att/f"call-{row['index']:02d}-prompt.txt")==row['prompt_sha256']
        if row['status']=='returned':assert sha(att/f"call-{row['index']:02d}-response.txt")==row['response_sha256']
    assert all(row['status']=='returned'for row in calls),'Audit failure outcomes separately'
    cursor=0;shared={};writer={};rows=[]
    for arm in plan['arms']:
        arm_sources=copy.deepcopy(sources);fetch=FixedSources();folder=a.out_dir/arm;folder.mkdir();trace=Trace(folder/'trace.jsonl')
        class Handler:
            stream_callback=None
            settings_snapshot=plan['settings']|{'citation.fresh_evidence_synthesis':arm=='fresh'}
            evidence_fetcher=fetch
            def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
            def is_fact_checking_enabled(self):return True
            def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
            def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
            def _no_sources_response(self,q):raise ValueError('No actual source material')
            def _invoke_text(self,prompt,trace=None,stage='model'):
                nonlocal cursor
                call=calls[cursor];cursor+=1;assert call['arm']==arm and call['stage']==stage
                assert (att/f"call-{call['index']:02d}-prompt.txt").read_text()==prompt,(arm,stage,call['index'])
                raw=(att/f"call-{call['index']:02d}-response.txt").read_text()
                if stage=='source_reading':
                    if arm=='fresh':assert shared.get(prompt)==raw and call['origin']=='strict_shared_source_reading'
                    else:shared[prompt]=raw
                if stage=='writer':writer[arm]=prompt
                return raw
        result=evidence_flow.synthesize(Handler(),case['query'],arm_sources,original,trace);actual=json.loads((att/arm/'result.json').read_text());assert result['content']==(att/arm/'report.txt').read_text();assert result['evidence_review']==actual['native_review'];assert arm_sources==actual['sources'];assert fetch.events==actual['supplement_requests']
        generated=next(x for x in calls if x['arm']==arm and x['stage']=='writer');raw=(att/f"call-{generated['index']:02d}-response.txt").read_text();body_exposure={s['index']:s['fetched_content']in writer[arm]for s in sources if s.get('fetched_content')};assert all(body_exposure.values())
        rows.append(dict(arm=arm,report_sha256=sha(att/arm/'report.txt'),report_chars=len(result['content']),raw_writer_sha256=generated['response_sha256'],raw_writer_chars=len(raw),native_changed_writer=result['content']!=raw,all_acquired_body_bytes_in_writer=body_exposure,review_status=result['evidence_review']['status'],unresolved_count=sum(len(x['unresolved'])for x in result['evidence_review']['parts']),applied_count=sum(len(x['applied'])for x in result['evidence_review']['parts'])))
    assert cursor==len(calls)and len(writer)==2
    assert writer['inherited'].split('New Sources:\n',1)[1]==writer['fresh'].split('New Sources:\n',1)[1]
    assert original in writer['inherited']and original not in writer['fresh']
    audit=dict(scope='Exact execution/provenance replay only; not independent correction/usefulness/new-error assessment',container_id=c['Id'],image=c['Image'],exit_code=0,read_only_workspace=True,launch_start_completion_hashes_match=True,all_prompt_reply_hashes_verified=True,all_native_prompts_parsers_application_and_complete_outputs_reproduced=True,pair_invariance=completion['pair_invariance'],arms=rows,logical_calls=len(calls),fresh_model_calls=sum(x['origin']=='fresh_model'for x in calls),strict_shared_reading_calls=sum(x['origin']=='strict_shared_source_reading'for x in calls),live_retrieval_reads=0,newly_credited_corrections=0)
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
