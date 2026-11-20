"""Terminal original-input/cache/render/native replay audit; not semantic scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from scripts.isolated_network import assert_network_matches
from research_verify.fact_document import instructions as flat_instructions
from research_verify.section_document import instructions,render


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--writer-run',type=Path,required=True);p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    inspect=lambda cid:json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    def terminal(folder):
        launch=json.loads((folder/'launch.json').read_text());info=inspect(launch['container_id']);ref=inspect(launch['network_reference_container'])
        assert info['State']['Status']=='exited'and info['State']['ExitCode']==0 and info['Image']==launch['image_id'];assert_network_matches(ref,info)
        assert info['Config']['Healthcheck']['Test']==['NONE']and info['Config']['Entrypoint']==['/install/.venv/bin/python']
        assert next(m for m in info['Mounts']if m['Destination']=='/workspace')['RW']is False
        overlay=lambda x:sorted((m['Source'],m['Destination'],m['RW'])for m in x['Mounts']if m['Destination'].startswith('/install/'))
        assert overlay(info)==overlay(ref)and len(overlay(info))==3 and all(not m[2]for m in overlay(info))
        freeze=json.loads((folder/'launch-freeze.json').read_text());assert all(sha(Path(k))==h for k,h in freeze.items())
        inner=json.loads((folder/'attempt/prestart-freeze.json').read_text())
        for k,h in inner.items():
            path=Path(k);host=Path.cwd()/path.relative_to('/workspace')if path.is_relative_to('/workspace')else path
            assert sha(host)==h
            if k.startswith(('scripts/','local_deep_research/')):assert sha(folder/'attempt/code'/k)==h
        return dict(container_id=launch['container_id'],image_id=info['Image'],exit_code=0,launch_frozen_files=len(freeze),prestart_frozen_files=len(inner),all_frozen_hashes_unchanged=True,reference_network_matches=True,repo_read_only=True,three_reference_overlays=True,healthcheck_disabled=True)
    writer_terminal=terminal(a.writer_run);native_terminal=terminal(a.run);writer=a.writer_run/'attempt';attempt=a.run/'attempt';plan=json.loads((attempt/'plan.json').read_text());prior=Path(plan['prior_attempt'])
    sources=json.loads((writer/'sources.json').read_text());registry=json.loads((writer/'fact-registry.json').read_text());oldcalls=json.loads((prior/'calls.json').read_text());oldwriter=next(c for c in oldcalls if c['arm']=='candidate'and c['stage']=='writer');oldprompt=(prior/f"call-{oldwriter['index']:02d}-prompt.txt").read_text();suffix=flat_instructions(sources,registry);assert oldprompt.endswith(suffix);prefix=oldprompt[:-len(suffix)]
    assert prefix==(writer/'native-writer-prefix.txt').read_text()and prefix==(prior/'call-01-prompt.txt').read_text()
    assert (writer/'prompt.txt').read_text()==prefix+instructions(sources,registry)
    assert (prior/'source-material.txt').read_text()in prefix
    raw=(writer/'response.txt').read_text();draft,receipts=render(raw,sources,registry);assert draft==(writer/'candidate-draft.txt').read_text()and receipts==json.loads((writer/'rendering.json').read_text())
    wr=json.loads((writer/'result.json').read_text());assert sha(writer/'response.txt')==wr['response_sha256']and sha(writer/'prompt.txt')==wr['prompt_sha256']
    calls=json.loads((attempt/'calls.json').read_text());assert [c['index']for c in calls]==list(range(len(calls)))
    for c in calls:
        assert c['status']=='returned'
        pp=attempt/f"call-{c['index']:02d}-prompt.txt";rp=attempt/f"call-{c['index']:02d}-response.txt";assert sha(pp)==c['prompt_sha256']and sha(rp)==c['response_sha256']
        if c['origin']in('strict_prior_cache','strict_writer_cache'):assert rp.read_bytes()==Path(c['cached_from']).read_bytes()
    candidate=next(c for c in calls if c['arm']=='section'and c['stage']=='writer');assert candidate['prompt_sha256']==wr['prompt_sha256']and candidate['response_sha256']==wr['response_sha256']and candidate['origin']=='strict_writer_cache'
    assert (attempt/'section/writer-rendered.txt').read_text()==draft
    assert (attempt/'flat/report.txt').read_bytes()==(prior/'candidate/report.txt').read_bytes()
    subprocess.run([sys.executable,'scripts/run_section_writer_pair_20261115.py','--prior-attempt',str(prior),'--out-dir',str(a.out_dir/'writer-replay'),'--replay-attempt',str(writer)],check=True)
    subprocess.run([sys.executable,'scripts/run_section_native_pair_20261115.py','--prior-attempt',str(prior),'--writer-attempt',str(writer),'--case-manifest',str(a.case_manifest),'--out-dir',str(a.out_dir/'native-replay'),'--replay-attempt',str(attempt)],check=True)
    assert json.loads((a.out_dir/'native-replay/completion.json').read_text())['replay_exact']
    fresh=[wr['response_metadata'],*[c['response_metadata']for c in calls if c['origin']=='fresh_model']]
    audit=dict(writer_terminal=writer_terminal,native_terminal=native_terminal,complete_original_source_material_in_identical_native_prefix=True,derived_writer_prefix_binding_verified=True,baseline_exact_saved_complete_report=True,candidate_writer_exactly_cached_once=True,fact_registry_unchanged=True,writer_rendering_exact=True,complete_saved_response_native_replay_exact=True,audit_new_model_calls=0,audit_new_retrieval_calls=0,fresh_calls_this_turn=len(fresh),fresh_finish_reasons=[m.get('finish_reason')for m in fresh],token_usage={k:sum(m.get('token_usage',{}).get(k,0)for m in fresh)for k in ['prompt_tokens','completion_tokens','total_tokens']},scientific_quality_assessed=False,new_independent_correction_credit=0)
    write(a.out_dir/'audit.json',audit);print(json.dumps(audit))


if __name__=='__main__':main()
