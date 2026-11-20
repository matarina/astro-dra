"""Finite original-locator acquisition/exposure, live or exact cached-byte replay."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.evidence_flow import supplement
from research_verify.generation import format_source_documents
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.experiment_error_receipt import error_receipt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--source-ids',type=int,nargs='+',required=True)
    p.add_argument('--mode',choices=['live','cache'],required=True)
    p.add_argument('--cache-attempt',type=Path);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--request-budget',type=int,
        help='1..8 logical reads; stable-ID article lookup can require metadata plus full-text XML')
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    if not 1<=len(a.source_ids)<=4 or len(set(a.source_ids))!=len(a.source_ids):raise ValueError('Probe source bound')
    request_budget=a.request_budget if a.request_budget is not None else len(a.source_ids)
    if not 1<=request_budget<=8:raise ValueError('Probe logical request bound')
    original=json.loads(a.sources.read_text());sources=copy.deepcopy(original)
    assert set(a.source_ids)<={int(s['index'])for s in sources}
    files=[a.sources,Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
        Path('scripts/run_native_original_report_pair_20261114.py'),Path('scripts/experiment_error_receipt.py'),
        Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    cache={}
    if a.mode=='cache':
        assert a.cache_attempt
        transport=a.cache_attempt/'primary-transport.json';files.append(transport)
        for event in json.loads(transport.read_text()):
            if event['status']=='retrieved':
                path=a.cache_attempt/event['file'];assert sha(path)==event['sha256'];files.append(path)
                cache[json.dumps([event['url'],event.get('params')],sort_keys=True)]=path.read_bytes()
        def get(url,**kw):
            raw=cache[json.dumps([url,kw.get('params')],sort_keys=True)]
            return SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[raw],close=lambda:None)
        settings={};get_transport=get
    else:
        from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
        defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
        settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});get_transport=None
    settings['citation.original_reference_document_followup']=True
    freeze={str(path):sha(path)for path in files}
    (a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in files:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    transport=[]
    class Recorded(EvidenceFetcher):
        def read_bytes(self,url,**kw):
            event=dict(index=len(transport),url=url,params=kw.get('params'),origin=a.mode);transport.append(event)
            try:
                raw=super().read_bytes(url,**kw);path=a.out_dir/f"response-{event['index']:02d}.bin";path.write_bytes(raw)
                event.update(status='retrieved',bytes=len(raw),file=path.name,sha256=sha(path));return raw
            except Exception as exc:event.update(status='unavailable',**error_receipt(exc));raise
    fetch=Recorded(settings,get=get_transport,seconds=45,requests=request_budget);trace=Trace(a.out_dir/'trace.jsonl')
    acquired=supplement([dict(status='insufficient_evidence',source_id=i,request={'kind':'article'})for i in a.source_ids],
        sources,fetch,register=None,trace=trace)
    # Keep successful and failed reads even if later formatting/validation fails.
    (a.out_dir/'primary-transport.json').write_text(json.dumps(transport,ensure_ascii=False,indent=2)+'\n')
    rows=[]
    for source in sources:
        if int(source['index'])not in acquired:continue
        path=a.out_dir/f"source-{source['index']}-text.txt";path.write_text(source['fetched_content'])
        material=format_source_documents(native_documents([source]),max_chars=60000,required_ids={int(source['index'])})
        view=material.views[int(source['index'])];assert view['block']in str(material)
        (a.out_dir/f"source-{source['index']}-material.txt").write_text(str(material))
        rows.append(dict(source_index=source['index'],text_sha256=sha(path),text_chars=len(source['fetched_content']),
            model_view_chars=view['model_view_chars'],scope=view['scope'],identity_warning_visible='NOT independently confirmed'in view['text']))
    assert all({k:v for k,v in before.items()if k!='fetched_content'}==
        {k:v for k,v in after.items()if k!='fetched_content'}
        for before,after in zip(original,sources,strict=True))
    assert all(before.get('fetched_content')==after.get('fetched_content')
        for before,after in zip(original,sources,strict=True)if int(before['index'])not in acquired)
    (a.out_dir/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    receipt=dict(scope='Finite locator document acquisition and native source formatting; no LLM/identity/quality acceptance',
        mode=a.mode,source_ids=a.source_ids,request_budget=request_budget,source_pack_sha256=sha(a.sources),acquired=acquired,transport=transport,views=rows,
        code_input_hashes_unchanged=all(sha(Path(path))==digest for path,digest in freeze.items()),
        original_metadata_preserved=True,model_calls=0,newly_credited_corrections=0,quality_claim=None)
    (a.out_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
