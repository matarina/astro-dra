"""Finite Europe PMC identifier lookups; metadata, not claim adjudication."""
import argparse
import hashlib
import json
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

from research_verify.bibliography_identity import match_identifiers


def expression(kind,value):
    if kind=='doi':return 'DOI:"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
    if kind=='pmid':return '(EXT_ID:'+value+' AND SRC:MED)'
    if kind=='pmcid':return 'PMCID:'+value
    return '(EXT_ID:'+value+' AND SRC:PPR)'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--crosswalk',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--ca-file',type=Path)
    parser.add_argument('--only-cached',action='store_true',help='Acquire core records for previously matched metadata-only cache entries')
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=False)
    cross=json.loads(args.crosswalk.read_text());queries=set()
    for report in cross['reports']:
        for row in report['entries']:
            identity=row['primary_cache']
            if identity['status']=='nonunique_bibliography_source_id':continue
            if (identity['status']=='one_record_match')!=args.only_cached:continue
            ids=identity['identifiers']
            if any(len(v)!=1 for v in ids.values()):continue
            for kind in ('doi','pmid','pmcid','ppr'):
                if ids.get(kind):queries.add((kind,ids[kind][0]));break
    batches=[sorted(queries)[i:i+20] for i in range(0,len(queries),20)]
    inputs=[args.crosswalk,Path(__file__),Path('local_deep_research/research_verify/bibliography_identity.py'),
            Path('local_deep_research/research_verify/report_syntax.py')]
    if args.ca_file:inputs.append(args.ca_file)
    freeze={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    for p in inputs[1:]:
        dest=args.out_dir/'code'/(p.name if p.is_absolute() else p)
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    (args.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    (args.out_dir/'lookup-plan.json').write_text(json.dumps(dict(scope='Metadata lookup only; no title search or new report evaluation',only_cached=args.only_cached,batches=batches,max_pages_per_batch=2,page_size=1000,timeout_seconds=30),indent=2)+'\n')
    if not args.execute:print('Plan only:',len(queries),'identifier queries');return
    tls_context=ssl.create_default_context(cafile=str(args.ca_file) if args.ca_file else None)
    calls=[];records={}
    for batch_index,batch in enumerate(batches):
        cursor='*'
        for page in range(2):
            query=' OR '.join('('+expression(kind,value)+')' for kind,value in batch)
            url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode(dict(query=query,format='json',resultType='core',pageSize=1000,cursorMark=cursor))
            row=dict(batch=batch_index,page=page,url=url)
            try:
                start=time.monotonic()
                with urlopen(Request(url,headers={'User-Agent':'Astro-DRA-identity-diagnostic/1.0'}),timeout=30,context=tls_context) as response:
                    body=response.read(20000001);row['http_status']=response.status
                if len(body)>20000000:raise ValueError('Response over bounded size')
                name=f'batch-{batch_index:02d}-page-{page:02d}.json';(args.out_dir/name).write_bytes(body)
                payload=json.loads(body);results=(payload.get('resultList') or {}).get('result')
                if not isinstance(results,list):raise ValueError('Missing API result list')
                for record in results:
                    if record.get('source') and record.get('id'):
                        records[str(record['source'])+':'+str(record['id'])]=record
                row.update(status='received',body_path=name,body_sha256=hashlib.sha256(body).hexdigest(),
                    hit_count=payload.get('hitCount'),records=len(results),elapsed_s=round(time.monotonic()-start,3))
                next_cursor=payload.get('nextCursorMark')
                if len(results)<1000 or not next_cursor or next_cursor==cursor:cursor=None
                else:cursor=next_cursor
            except Exception as exc:
                row.update(status='unavailable',error_type=type(exc).__name__,error=str(exc)[:250]);cursor=None
            calls.append(row);(args.out_dir/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2)+'\n')
            if cursor is None:break
    reports=[]
    for report in cross['reports']:
        rows=[]
        for row in report['entries']:
            ids=row['primary_cache']['identifiers']
            if row['primary_cache']['status']=='nonunique_bibliography_source_id' or any(len(v)!=1 for v in ids.values()):
                mapping=dict(status='ambiguous_original_identifiers',identifiers=ids,matches=[],conflicts=[])
            else:mapping=match_identifiers({key:values[0] for key,values in ids.items()},records)
            rows.append(dict(source_id=row['source_id'],mapping=mapping))
        # Previous cached metadata is separate and is not silently replaced.
        reports.append(dict(report_path=report['report_path'],entries=rows))
    out=dict(scope='Europe PMC API metadata and exact identifier matching only; missing/ambiguous records are unresolved, not evidence of nonexistence',
        queries=len(queries),http_calls=len(calls),failed_calls=sum(c['status']!='received' for c in calls),records=records,
        reports=reports,frozen_inputs_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in freeze.items()),quality_claim=None)
    (args.out_dir/'metadata.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(queries=len(queries),calls=len(calls),records=len(records),failed=out['failed_calls'])))


if __name__=='__main__':main()
