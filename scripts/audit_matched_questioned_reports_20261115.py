"""Terminal, source-body binding and complete saved-response replay audit.

Engineering provenance only; no scientific credit or production operations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from research_verify.pmc_identity import article_text
from scripts.isolated_network import assert_network_matches


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    a=parser.parse_args();a.out_dir.mkdir(exist_ok=False)
    launch=json.loads((a.run/'launch.json').read_text())
    inspect=lambda cid:json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    info=inspect(launch['container_id']);ref=inspect(launch['network_reference_container'])
    assert info['State']['Status']=='exited' and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id']
    assert_network_matches(ref,info)
    assert info['Config']['Healthcheck']['Test']==['NONE']
    assert info['Config']['Entrypoint']==['/install/.venv/bin/python']
    repo=next(m for m in info['Mounts'] if m['Destination']=='/workspace')
    assert repo['RW'] is False and Path(repo['Source']).resolve()==Path.cwd().resolve()
    overlays=[m for m in info['Mounts']if m['Destination'].startswith('/install/')]
    assert len(overlays)==3 and all(not m['RW']for m in overlays)
    ref_overlays=[m for m in ref['Mounts']if m['Destination'].startswith('/install/')]
    assert sorted((m['Source'],m['Destination'])for m in overlays)==sorted((m['Source'],m['Destination'])for m in ref_overlays)
    start=json.loads((a.run/'launch-freeze.json').read_text())
    attempt=a.run/'attempt';inner=json.loads((attempt/'prestart-freeze.json').read_text())
    def host_path(value):
        path=Path(value)
        if path.is_relative_to('/workspace'):return Path.cwd()/path.relative_to('/workspace')
        if path.is_relative_to('/output'):return a.run/path.relative_to('/output')
        return path
    assert all(sha(Path(p))==h for p,h in start.items())
    assert all(sha(host_path(p))==h for p,h in inner.items())
    for p,h in inner.items():
        if p.startswith(('scripts/','local_deep_research/')):assert sha(attempt/'code'/p)==h
    binding=json.loads((a.inputs/'body-bindings.json').read_text())
    assert sha(Path(binding['base_sourcepack']))==binding['base_sha256']
    before=json.loads(Path(binding['base_sourcepack']).read_text());after=json.loads((a.inputs/'sources.json').read_text())
    assert [s['index']for s in before]==[s['index']for s in after]
    byid={str(s['index']):s for s in after};changed={}
    for b,new in zip(before,after):
        assert all(new[k]==v for k,v in b.items())
        extra=set(new)-set(b)
        assert extra in (set(),{'fetched_content'})
        if extra:changed[str(new['index'])]=new['fetched_content']
    assert set(changed)=={str(b['source_id'])for b in binding['bindings']}
    views=json.loads((attempt/'source-views.json').read_text());material=(attempt/'source-material.txt').read_text()
    for b in binding['bindings']:
        p=Path(b['xml_path']);assert sha(p)==b['xml_sha256']
        tree=ET.fromstring(p.read_bytes());meta=tree.find('./front/article-meta')
        own={n.get('pub-id-type'):''.join(n.itertext()).strip()for n in meta.findall('./article-id')}
        assert own==b['own_article_ids']
        sid=str(b['source_id']);s=byid[sid]
        assert own['pmid']==s['pmid'] and own['doi'].lower()==s['doi'].lower()
        value=article_text(p.read_bytes(),{'pmcid':own['pmcid'],'doi':own['doi']},pmid=own['pmid'],require_body=True)
        assert value==changed[sid] and len(value)==b['body_chars']
        assert hashlib.sha256(value.encode()).hexdigest()==b['body_sha256']
        view=views[sid];assert value in view['text'] and view['text']in material
        assert view['model_view_chars']==view['available_chars']
    calls=json.loads((attempt/'calls.json').read_text());assert [c['index']for c in calls]==list(range(len(calls)))
    for c in calls:
        assert c['status']=='returned'
        assert sha(attempt/f"call-{c['index']:02d}-prompt.txt")==c['prompt_sha256']
        assert sha(attempt/f"call-{c['index']:02d}-response.txt")==c['response_sha256']
    writers={c['arm']:c for c in calls if c['stage']=='writer'}
    wp=lambda arm:(attempt/f"call-{writers[arm]['index']:02d}-prompt.txt").read_text()
    assert wp('candidate').startswith(wp('baseline')) and material in wp('baseline')
    reader=[c for c in calls if c['stage']=='source_reading']
    assert len(reader)==2 and reader[0]['prompt_sha256']==reader[1]['prompt_sha256'] and reader[0]['response_sha256']==reader[1]['response_sha256']
    assert reader[1]['origin']=='strict_shared_source_reading'
    completion=json.loads((attempt/'completion.json').read_text())
    assert completion['frozen_inputs_unchanged'] and all(r['status']=='completed'for r in completion['arms'])
    replay=a.out_dir/'replay'
    subprocess.run([sys.executable,'scripts/run_matched_questioned_reports_20261115.py','--case-manifest',str(a.inputs/'case-manifest.json'),'--out-dir',str(replay),'--replay-attempt',str(attempt)],check=True)
    replay_completion=json.loads((replay/'completion.json').read_text());assert replay_completion['replay_exact'] and replay_completion['fresh_model_requests']==0
    receipts=dict(container_id=launch['container_id'],terminal_exit=0,image_id=info['Image'],network_matches_reference=True,repo_read_only=True,healthcheck_disabled=True,standard_read_only_overlays=3,launch_frozen_files=len(start),prestart_frozen_files=len(inner),all_frozen_hashes_unchanged=True,stable_source_count=len(after),own_primary_article_bodies_verified=len(changed),body_ids=sorted(changed),complete_acquired_body_exposure_both_arms=True,logical_calls=len(calls),fresh_model_calls=completion['fresh_model_requests'],shared_calls=completion['strict_shared_calls'],finish_reasons=[c['response_metadata'].get('finish_reason')for c in calls],complete_saved_response_native_replay_exact=True,audit_new_model_calls=0,audit_new_retrieval_calls=0,new_independent_correction_credit=0,scientific_status='not_independently_assessed')
    write(a.out_dir/'audit.json',receipts);print(json.dumps(receipts))


if __name__=='__main__':main()
