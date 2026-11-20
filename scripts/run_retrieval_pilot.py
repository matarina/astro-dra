"""Live native preview retrieval with transport evidence; no relevance gold claim."""
import json
import hashlib
import os
import time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs


def main():
    from loguru import logger
    logger.remove()
    import requests
    from local_deep_research.web_search_engines.engines.search_engine_pubmed import PubMedSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_europepmc import EuropePMCSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_searxng import SearXNGSearchEngine
    from research_verify.source_identity import identity_fields
    root=Path('/experiment');cfg=json.loads((root/'experiment.json').read_text());arm=os.environ['PILOT_ARM'];out=root/arm;out.mkdir(exist_ok=True)
    requests_seen=[];send=requests.sessions.Session.send
    def capture(self,request,**kwargs):
        url=urlsplit(request.url);begin=time.monotonic()
        # Never store authentication, proxy headers, cookies or API keys.
        row={'host':url.hostname,'path':url.path,'params':{k:v for k,v in parse_qs(url.query).items() if k in {'query','term','q','format','retmax','pageSize','id','engines'}},'request_number':len(requests_seen)}
        requests_seen.append(row)
        try:
            response=send(self,request,**kwargs);row.update(status_code=response.status_code,latency_seconds=time.monotonic()-begin)
            payload=response.content;name='response-'+str(row['request_number'])+'.bin';(out/name).write_bytes(payload);row.update(file=name,sha256=hashlib.sha256(payload).hexdigest());return response
        except Exception as exc:
            row.update(error_type=type(exc).__name__,latency_seconds=time.monotonic()-begin);raise
    requests.sessions.Session.send=capture
    selected=(os.environ['PILOT_ENGINES'].split(',') if os.environ.get('PILOT_ENGINES')
              else cfg['engines'] if arm=='baseline' else ['pubmed'])
    for engine in selected:
        for case in cfg['cases']:
            target=out/(engine+'-'+case['case_id']+'.json')
            if target.exists():continue
            before=len(requests_seen);start=time.monotonic();obj=None
            row={**case,'engine':engine,'arm':arm,'preview_budget':cfg['max_results']}
            try:
                if engine=='pubmed':obj=PubMedSearchEngine(max_results=cfg['max_results'],llm=None,optimize_queries=False,get_full_text=False)
                elif engine=='europepmc':obj=EuropePMCSearchEngine(max_results=cfg['max_results'],llm=None,programmatic_mode=True)
                else:
                    row['instance']=os.environ.get('SEARXNG_EVAL_INSTANCE',cfg['searxng_instance'])
                    row['backends']=os.environ.get('SEARXNG_EVAL_BACKENDS','').split(',') if os.environ.get('SEARXNG_EVAL_BACKENDS') else None
                    obj=SearXNGSearchEngine(max_results=cfg['max_results'],llm=None,instance_url=row['instance'],engines=row['backends'],result_format='json',include_full_content=False,programmatic_mode=True)
                results=obj._get_previews(case['query']);matches=[]
                for rank,source in enumerate(results,1):
                    ids=identity_fields(source)
                    if ids.get('pmid')==case['expected_pmid'] or ids.get('doi','').casefold()==case['expected_doi'].casefold():matches.append(rank)
                row.update(status='completed',returned_count=len(results),target_ranks=matches,known_item_hit=bool(matches),sources=results)
            except Exception as exc:row.update(status='error',error_type=type(exc).__name__)
            finally:
                if obj and hasattr(obj,'close'):
                    try:obj.close()
                    except Exception:pass
            row.update(latency_seconds=time.monotonic()-start,requests=requests_seen[before:])
            # A swallowed engine error is still visible as failed transport.
            row['transport_failures']=sum(x.get('status_code',200)>=400 or 'error_type' in x for x in row['requests'])
            target.write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str));print(json.dumps({k:row.get(k) for k in ('engine','case_id','status','returned_count','known_item_hit','transport_failures','latency_seconds')}),flush=True)


if __name__=='__main__':main()
