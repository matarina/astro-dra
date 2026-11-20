"""Audit a terminal fact-document attempt; replay with saved responses only."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

from research_verify import evidence_flow
from research_verify.fact_document import render, instructions, answer_prompt, parse_answers
from scripts.isolated_network import assert_network_matches
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--case-manifest',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    a=p.parse_args();run=a.run;attempt=run/'attempt'
    launch=json.loads((run/'launch.json').read_text())
    info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    assert info['State']['Status']=='exited'and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id']
    reference=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    assert_network_matches(reference,info)
    assert info['Config']['Healthcheck']['Test']==['NONE']
    assert any(m['Destination']=='/workspace'and not m['RW']for m in info['Mounts'])
    checks=[]
    for name in ['launch-freeze.json','attempt/prestart-freeze.json']:
        for k,v in json.loads((run/name).read_text()).items():
            path=Path(k.removeprefix('/workspace/'));assert sha(path)==v,(name,k)
            checks.append(dict(path=k,sha256=v,freeze=name))
    completion=json.loads((attempt/'completion.json').read_text())
    assert completion['frozen_inputs_unchanged']and all(r['status']=='completed'for r in completion['arms'])
    case=_manifest_cases(a.case_manifest)[0];sources=json.loads(case['source'].read_text())
    calls=json.loads((attempt/'calls.json').read_text());fresh=[c for c in calls if c['origin']=='fresh_model']
    usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)
    for c in calls:
        assert c['status']=='returned'
        assert sha(attempt/f"call-{c['index']:02d}-prompt.txt")==c['prompt_sha256']
        assert sha(attempt/f"call-{c['index']:02d}-response.txt")==c['response_sha256']
        assert c['response_metadata']['finish_reason']=='stop'
        if c in fresh:
            for key in usage:usage[key]+=c['response_metadata']['token_usage'][key]
    batches=json.loads((attempt/'source-answer-batches.json').read_text());registry={}
    source_calls=[c for c in calls if c['stage']=='source_answers'];assert len(source_calls)==len(batches)==4
    for batch_index,(batch,c) in enumerate(zip(batches,source_calls)):
        assert answer_prompt(case['query'],batch)==(attempt/f"call-{c['index']:02d}-prompt.txt").read_text()
        parsed=parse_answers((attempt/f"call-{c['index']:02d}-response.txt").read_text(),batch)
        assert parsed==json.loads((attempt/f'fact_document/source-answers-{batch_index:02d}.json').read_text())
        assert not set(registry)&set(parsed['registry']);registry.update(parsed['registry'])
    assert registry==json.loads((attempt/'fact_document/fact-registry.json').read_text())
    candidate=[c for c in calls if c['arm']=='fact_document' and c['stage']!='source_answers']
    writer=next(c for c in candidate if c['stage']=='writer')
    rendered,receipts=render((attempt/f"call-{writer['index']:02d}-response.txt").read_text(),sources,registry)
    assert rendered==(attempt/'fact_document/writer-rendered.txt').read_text()
    assert receipts==json.loads((attempt/'fact_document/fact-rendering.json').read_text())
    a.out_dir.mkdir(exist_ok=False)
    prior=json.loads((attempt/'plan.json').read_text())
    oldplan=json.loads((Path(prior['prior_attempt'])/'plan.json').read_text())
    clock=datetime.fromisoformat(oldplan['fixed_writer_clock'])
    class FixedClock:
        @staticmethod
        def now(tz=None):return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime=FixedClock
    fetch=FixedSources();arm_sources=copy.deepcopy(sources);position=0
    class Handler:
        stream_callback=None
        settings_snapshot=prior['settings']
        evidence_fetcher=fetch
        def get_setting(self,k,d=None):return self.settings_snapshot.get(k,d)
        def is_fact_checking_enabled(self):return True
        def _get_output_instruction_prefix(self):return '请用中文回答原始用户问题。\n'
        def _create_documents(self,sources,nr_of_links=0):return native_documents(sources)
        def _no_sources_response(self,q):raise ValueError('No source material')
        def _invoke_text(self,prompt,trace=None,stage='model'):
            nonlocal position
            c=candidate[position];position+=1;assert c['stage']==stage
            expected=(attempt/f"call-{c['index']:02d}-prompt.txt").read_text()
            assert (prompt+instructions(arm_sources,registry)if stage=='writer'else prompt)==expected
            raw=(attempt/f"call-{c['index']:02d}-response.txt").read_text()
            return render(raw,arm_sources,registry)[0]if stage=='writer'else raw
    replay=evidence_flow.synthesize(Handler(),case['query'],arm_sources,case['draft'].read_text(),Trace(a.out_dir/'replay-trace.jsonl'))
    saved=json.loads((attempt/'fact_document/result.json').read_text())
    assert position==len(candidate)and replay['content']==(attempt/'fact_document/report.txt').read_text()
    assert replay['evidence_review']==saved['native_review']and fetch.events==saved['supplement_requests']
    audit=dict(scope='Engineering transport, source-answer/field provenance and full native replay only; no independent scientific judgement',container_id=launch['container_id'],image_id=info['Image'],exit_code=0,
               frozen_hash_checks=checks,logical_calls=len(calls),fresh_model_requests=len(fresh),strict_cached_calls=len(calls)-len(fresh),fresh_token_usage=usage,
               fact_nodes=len(receipts['facts']),identity_nodes=len(receipts['identities']),source_answer_facts=len(registry),unselected_facts=len(receipts['unselected_fact_ids']),fact_rendering_replay_exact=True,whole_native_replay_exact=True,
               baseline_report_sha256=sha(attempt/'baseline/report.txt'),candidate_report_sha256=sha(attempt/'fact_document/report.txt'),
               baseline_chars=len((attempt/'baseline/report.txt').read_text()),candidate_chars=len(replay['content']),
               candidate_applied=sum(len(part.get('applied',[]))for part in saved['native_review'].get('parts',[])),
               candidate_unresolved=sum(len(part.get('unresolved',[]))for part in saved['native_review'].get('parts',[])),
               retrieval_reads=0,newly_credited_corrections=0,
               limit='Exact copying of fallible source answers does not prove their truth, quote entailment, selection fitness, free synthesis correctness, useful retention or generalization')
    (a.out_dir/'terminal-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items()if k not in ['frozen_hash_checks','limit','scope']}))


if __name__=='__main__':main()
