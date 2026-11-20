"""Isolated full-source selection diagnostic, never a report/verification runner."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from research_verify.generation import source_material
from research_verify.source_reader_candidate import source_segments, reading_batches, read_source, read_source_details


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-pack', type=Path, required=True)
    p.add_argument('--query-file', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--details', action='store_true')
    p.add_argument('--detail-indices', action='store_true')
    args = p.parse_args()
    query = args.query_file.read_text()
    sources = json.loads(args.source_pack.read_text())['sources']
    code = ['local_deep_research/research_verify/source_reader_candidate.py',
            'local_deep_research/research_verify/generation.py',
            'scripts/run_full_source_reader_candidate_20261114.py']
    freeze = dict(code_sha256={s:sha(s) for s in code},source_pack_sha256=sha(args.source_pack),
                  query_sha256=sha(args.query_file))
    prepared = [(s, source_material(s)[0]) for s in sources]
    preflight = dict(freeze=freeze,sources=[dict(source_id=s['index'],chars=len(t),
                    segments=len(source_segments(t)),batches=len(reading_batches(source_segments(t))))
                    for s,t in prepared],execute=args.execute,details=args.details,detail_indices=args.detail_indices)
    preflight['planned_calls'] = sum(s['batches'] for s in preflight['sources'])
    args.out_dir.mkdir(parents=True,exist_ok=False)
    (args.out_dir/'prestart-freeze.json').write_text(json.dumps(preflight,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(sources=len(sources),chars=sum(len(t) for _,t in prepared),planned_calls=preflight['planned_calls'])),flush=True)
    if not args.execute:
        return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.config.llm_config import get_llm
    values = json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snapshot = apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in values.items()})
    snapshot.update({'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash',
                     'llm.temperature':0,'llm.max_tokens':2500 if args.details else 500,'llm.request_timeout':120,'llm.max_retries':1})
    def setting(key,default=None):
        return snapshot.get(key,default)
    started=time.time()
    receipts=[]
    with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(setting)})()):
        model=get_llm(settings_snapshot=snapshot)
        for ordinal,(source,text) in enumerate(prepared):
            path=args.out_dir/f'source-{ordinal:03d}.json'
            with (args.out_dir/'calls.jsonl').open('a') as log:
                def record(entry):
                    log.write(json.dumps(dict(source_id=source['index'],**entry),ensure_ascii=False)+'\n');log.flush()
                reader=read_source_details if args.details else read_source
                extra={'concrete_details':True} if args.detail_indices and not args.details else {}
                receipt=reader(query,source['index'],source.get('title',''),text,model.invoke,record=record,**extra)
            path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
            receipts.append(dict(source_id=source['index'],path=path.name,sha256=sha(path),
                                 unread=len(receipt['unread_segment_indices']),selected=len(receipt['selected_segment_indices']),
                                 spans=len(receipt['spans']),selected_chars=sum(len(s['text']) for s in receipt['spans'])))
            print(json.dumps(receipts[-1]),flush=True)
    summary=dict(status='completed',elapsed_s=round(time.time()-started,3),sources=receipts,
                 planned_calls=preflight['planned_calls'],freeze=freeze,
                 completion_code_sha256={s:sha(s) for s in code},quality_claim=None,
                 scope='Relevance/coverage diagnostic only; no report or support/correction assessment')
    (args.out_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
