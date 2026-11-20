"""Offline canonical-interval replay; keep original reader output immutable."""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.generation import source_material
from research_verify.source_reader_candidate import source_segments,reading_batches,detail_reading_prompt,request_fields
from research_verify.source_quote_anchors import locate_quote_hint


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--reader-dir',type=Path,required=True)
    p.add_argument('--source-pack',type=Path,required=True)
    p.add_argument('--query-file',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    args=p.parse_args();args.out_dir.mkdir(parents=True,exist_ok=False)
    query=args.query_file.read_text();sources=json.loads(args.source_pack.read_text())['sources']
    originals={str(r['index']):r for r in sources};summary=[]
    for path in sorted(args.reader_dir.glob('source-*.json')):
        old=json.loads(path.read_text());s=originals[str(old['source_id'])];text=source_material(s)[0]
        assert hashlib.sha256(text.encode()).hexdigest()==old['source_sha256']
        batches=reading_batches(source_segments(text));spans={};rejected=[]
        for call in old['calls']:
            if call['status']!='completed':
                continue
            batch=batches[call['batch']]
            assert detail_reading_prompt(query,s.get('title',''),batch)==call['prompt']
            raw=call['raw_response'].strip()
            if raw.startswith('```'):
                raw=raw.split('\n',1)[1].rsplit('```',1)[0].strip()
            for row in json.loads(raw)['passages']:
                indices=row.get('field_indices');hint=row.get('quote')
                if (not isinstance(indices,list) or not indices or
                        any(type(i) is not int or not 0<=i<len(request_fields(query)) for i in indices)
                        or not isinstance(hint,str) or not 20<=len(hint)<=1600):
                    rejected.append(dict(batch=call['batch'],reason='invalid_quote_or_fields'));continue
                span=locate_quote_hint(hint,text,view_start=min(r['start'] for r in batch),
                                      view_end=max(r['end'] for r in batch))
                if span is None:
                    rejected.append(dict(batch=call['batch'],reason='unlocated_or_ambiguous'));continue
                span['fields']=[request_fields(query)[i] for i in sorted(set(indices))]
                key=(span['start'],span['end'])
                if key in spans:
                    span['fields']=sorted(set(span['fields'])|set(spans[key]['fields']))
                spans[key]=span
        rows=[spans[k] for k in sorted(spans)]
        receipt=dict(source_id=old['source_id'],source_sha256=old['source_sha256'],
                     request_sha256=old['request_sha256'],reader_receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     spans=rows,rejected=rejected,unread_segment_indices=old['unread_segment_indices'],
                     note='Source-original candidates from exact or unique boundary anchors; raw model wording is never evidence. No support verdict.')
        (args.out_dir/path.name).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        summary.append(dict(source_id=old['source_id'],spans=len(rows),chars=sum(len(r['text']) for r in rows),
                            anchored=sum(not r['hint_verbatim'] for r in rows),unread=len(old['unread_segment_indices'])))
    out=dict(scope='Offline source interval localization only; no new model/report call or corrected issue score',
             sources=summary,code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
             [Path(__file__),Path('local_deep_research/research_verify/source_quote_anchors.py')]},quality_claim=None)
    (args.out_dir/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(spans=sum(r['spans'] for r in summary),chars=sum(r['chars'] for r in summary),
                         anchored=sum(r['anchored'] for r in summary))))


if __name__=='__main__':main()
