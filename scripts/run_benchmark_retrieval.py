"""Per-engine native preview retrieval against an incomplete expert-known pool."""
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit,parse_qs


def main():
    from loguru import logger
    logger.remove()
    import requests
    from local_deep_research.web_search_engines.engines.search_engine_pubmed import PubMedSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_europepmc import EuropePMCSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_searxng import SearXNGSearchEngine
    from research_verify.source_identity import identity_fields
    root=Path("/experiment")
    protocol=json.loads((root/"retrieval-protocol.json").read_text())
    for name,expected in protocol["sha256"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError("Retrieval input changed: "+name)
    cfg=json.loads((root/"experiment.json").read_text())
    gold={r["task_family"]:r for r in json.loads((root/"reference-gold.json").read_text())}
    arm=os.environ["PILOT_ARM"]
    out=root/"retrieval"/arm
    out.mkdir(parents=True,exist_ok=True)
    seen=[]
    send=requests.sessions.Session.send
    def capture(self,request,**kwargs):
        url=urlsplit(request.url)
        event={"host":url.hostname,"path":url.path,"params":{k:v for k,v in parse_qs(url.query).items()
            if k in {"query","q","term","retmax","pageSize","id","format","engines"}}}
        seen.append(event)
        start=time.monotonic()
        try:
            response=send(self,request,**kwargs)
            name="response-"+str(len(seen)-1)+".bin"
            (out/name).write_bytes(response.content)
            event.update(status_code=response.status_code,file=name,sha256=hashlib.sha256(response.content).hexdigest())
            return response
        except Exception as error:
            event.update(error_type=type(error).__name__)
            raise
        finally:
            event["latency_seconds"]=time.monotonic()-start
    requests.sessions.Session.send=capture
    cases=[c for c in cfg["cases"] if c["variant"]=="original" and c["domain"]!="nlp_control"]
    for engine in protocol["engines"]:
        for case in (cases if arm=="baseline" else list(reversed(cases))):
            dest=out/(engine+"-"+case["case_id"]+".json")
            if dest.exists():
                raise ValueError("Do not overwrite an existing retrieval result")
            before=len(seen)
            start=time.monotonic()
            obj=None
            row={"case_id":case["case_id"],"task_family":case["task_family"],"domain":case["domain"],
                "arm":arm,"engine":engine,"query":gold[case["task_family"]]["original_reference"]["body"],
                "budget":protocol["preview_budget"]}
            try:
                if engine=="pubmed":
                    obj=PubMedSearchEngine(max_results=row["budget"],llm=None,optimize_queries=False,get_full_text=False)
                elif engine=="europepmc":
                    obj=EuropePMCSearchEngine(max_results=row["budget"],llm=None,programmatic_mode=True)
                else:
                    obj=SearXNGSearchEngine(max_results=row["budget"],llm=None,instance_url=protocol["searxng_instance"],
                        result_format="json",include_full_content=False,programmatic_mode=True)
                sources=obj._get_previews(row["query"])
                expert=set(gold[case["task_family"]]["known_pool_pmids"])
                pack=json.loads((root/case["source_pack"]).read_text())
                doi_to_pmid={s["doi"].casefold():s["pmid"] for s in pack if s.get("doi")}
                hits=[]
                for rank,source in enumerate(sources,1):
                    identifiers=identity_fields(source)
                    pmid=identifiers.get("pmid") or doi_to_pmid.get(identifiers.get("doi","").casefold())
                    if pmid in expert:
                        hits.append({"rank":rank,"pmid":pmid})
                row.update(status="completed",sources=sources,returned=len(sources),known_pool_hits=hits,
                    known_pool_numerator=len({h["pmid"] for h in hits}),known_pool_denominator=len(expert))
            except Exception as error:
                row.update(status="failed",error_type=type(error).__name__)
            finally:
                if obj and hasattr(obj,"close"):
                    try:obj.close()
                    except Exception:pass
            row.update(latency_seconds=time.monotonic()-start,requests=seen[before:])
            dest.write_text(json.dumps(row,ensure_ascii=False,indent=2,default=str)+"\n")
            print(json.dumps({k:row.get(k) for k in ["arm","engine","case_id","status","returned","known_pool_numerator","known_pool_denominator","latency_seconds"]}),flush=True)


if __name__=="__main__":
    main()
