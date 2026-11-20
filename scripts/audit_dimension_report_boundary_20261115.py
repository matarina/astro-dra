"""Terminal integrity/whole-context/zero-fresh replay; semantic judgments remain unassessed."""
import json,subprocess,collections
from pathlib import Path
from scripts.run_dimension_report_boundary_20261115 import prepare,read,write,sha,R
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.dimension_comparison import dimension_comparison_prompt,parse_dimension_comparisons,preview_confirmation_prompt
from research_verify.field_comparison import (comparison_prompt,parse_comparisons,edit_prompt,parse_edits,
    edit_confirmation_prompt,apply_confirmed_edits)

def main():
    root=R/'dimension-report-boundary-model-20261115-v2';attempt=root/'attempt';launch=read(root/'launch.json')
    runtime,=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))
    assert runtime['State']['Status']=='exited'and runtime['State']['ExitCode']==0 and runtime['Image']==launch['image_id']
    assert runtime['Config']['Healthcheck']['Test']==['NONE']and runtime['HostConfig']['NetworkMode']=='host'
    binds=[m for m in runtime['Mounts']if m['Type']=='bind'];assert sum(m['RW']for m in binds)==1
    assert next(m for m in binds if m['RW'])['Source']==str(root.resolve())
    for item in read(root/'readonly-mount-freeze.json'):
        m,=[m for m in binds if m['Destination']==item['destination']];assert not m['RW']and m['Source']==item['source']
        if item['sha256']:assert sha(Path(item['source']))==item['sha256']
    for name,h in read(attempt/'prestart-freeze.json').items():
        path=Path(name)
        if str(path).startswith('/workspace/'):path=Path.cwd()/path.relative_to('/workspace')
        assert sha(path)==h
        try:rel=path.resolve().relative_to(Path.cwd())
        except ValueError:continue
        if str(rel).startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/rel)==h
    completion=read(attempt/'completion.json');assert completion['status']=='completed_dimension_diagnostic'and completion['frozen_inputs_unchanged']
    calls=read(attempt/'calls.json');assert 5<=len(calls)<=6 and completion['fresh_calls']==len(calls)
    usage=collections.Counter()
    for i,row in enumerate(calls):
        assert row['index']==i and row['status']=='returned'and row['origin']=='fresh_model'and row['response_metadata']['finish_reason']=='stop'
        assert sha(attempt/f'call-{i:02d}-prompt.txt')==row['prompt_sha256']and sha(attempt/f'call-{i:02d}-response.txt')==row['response_sha256']
        usage.update({k:v for k,v in row['response_metadata']['token_usage'].items()if type(v)is int})
    cases,_=prepare();cursor=0;results=[];statistics=[]
    out=R/'dimension-report-boundary-terminal-audit-20261115-v2';out.mkdir(exist_ok=False)
    def invoke(prompt,case_id,stage,c):
        nonlocal cursor
        row=calls[cursor];assert row['case_id']==case_id and row['stage']==stage
        assert prompt==(attempt/f'call-{cursor:02d}-prompt.txt').read_text()
        assert c['report']in prompt and str(c['material'])in prompt
        raw=(attempt/f'call-{cursor:02d}-response.txt').read_text();cursor+=1;return raw
    n=0
    for c in cases:
        values=[c[k]for k in ['question','report','material','requirements','anchors','observations']]
        for arm,fn in [('existing_comparison',comparison_prompt),('dimension_comparison',dimension_comparison_prompt)]:
            prompt=fn(*values);assert prompt==(R/'dimension-report-boundary-preflight-20261115-v2/attempt'/f'prepared-{n:02d}-prompt.txt').read_text()
            raw=invoke(prompt,c['case_id'],arm,c)
            if arm=='existing_comparison':parsed=parse_comparisons(raw,c['question'],c['anchors'],c['observations'])
            else:parsed=parse_dimension_comparisons(raw,c['question'],c['material'],c['anchors'],c['observations'])
            row=dict(case_id=c['case_id'],arm=arm,comparisons=parsed);results.append(row)
            statistics.append(dict(case_id=c['case_id'],arm=arm,states=dict(collections.Counter(p['state']for p in parsed)),
                dimension_summary_disagreements=sum(p.get('dimension_summary_disagreement',False)for p in parsed),
                original_report_chars=len(c['report']),source_chars=len(str(c['material']))))
            n+=1
    assert results==completion['results']
    c=cases[0];values=[c[k]for k in ['question','report','material','requirements','anchors','observations']];comparisons=results[1]['comparisons']
    edits=parse_edits(invoke(edit_prompt(*values,comparisons),c['case_id'],'dimension_edit_proposals',c),c['report'],c['material'],c['requirements'],c['anchors'],c['source_ids'],c['observations'])
    answer=c['report'];changes=[];decisions=[]
    if edits['eligible']:
        prompt=preview_confirmation_prompt(edit_confirmation_prompt(*values,comparisons,edits['eligible']),c['report'],edits['eligible'])
        answer,changes,decisions=apply_confirmed_edits(invoke(prompt,c['case_id'],'dimension_preview_confirmation',c),c['report'],edits['eligible'])
    result=dict(proposals=edits,decisions=decisions,changes=changes,report_sha256=sha(attempt/'case-00/candidate-report.txt'),final_report_independently_assessed=False,final_subset_rechecked=False,independent_correction_credit=0)
    assert result==read(attempt/'case-00/edit-result.json')and answer==(attempt/'case-00/candidate-report.txt').read_text()and cursor==len(calls)
    write(out/'strict-replay-results.json',results);write(out/'strict-replay-edits.json',result);(out/'strict-replay-report.txt').write_text(answer)
    write(out/'runtime.json',dict(image=runtime['Image'],state=runtime['State'],mounts=runtime['Mounts'],network=runtime['HostConfig']['NetworkMode'],healthcheck=runtime['Config']['Healthcheck']))
    write(out/'audit.json',dict(scope=__doc__,fresh_calls=len(calls),strict_replay_fresh_calls=0,all_prompts_complete_original_report_and_actual_source=True,
        usage=dict(usage),statistics=statistics,model_confirmed_edits=len(changes),report_chars=len(answer),independent_correction_credit=0))
    (out/'audit-code.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),usage=dict(usage),statistics=statistics,model_confirmed_edits=len(changes),
        manifests={str(p):seal(p)for p in [R/'dimension-report-boundary-preflight-20261115-v2',root,out]}),ensure_ascii=False))

if __name__=='__main__':main()
