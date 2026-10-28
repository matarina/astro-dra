#!/usr/bin/env python3
"""Disposable-container E2E: live PubMed/model, real strategy/generator/storage/export."""
import json
import sys
import time
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone

config=json.loads(sys.stdin.read())
CALLS=[]
from loguru import logger
logger.remove()
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from local_deep_research.search_system import AdvancedSearchSystem
from local_deep_research.web_search_engines.engines.search_engine_pubmed import PubMedSearchEngine
from local_deep_research.report_generator import IntegratedReportGenerator
from local_deep_research.storage.database import DatabaseReportStorage
from local_deep_research.storage.file import FileReportStorage
from local_deep_research.database.models import ResearchHistory
from local_deep_research.database.models.base import Base
from local_deep_research.config.thread_settings import settings_context
from local_deep_research.web.services.report_assembly_service import assemble_full_report
from local_deep_research.web.services.research_service import export_report_to_memory, _extract_synthesized_answer
from research_verify.publication import publish_report,publication_for_report,validate_publication,KEY,digest
from research_verify.config import VerifyConfig
from research_verify.evidence import source_artifacts
from local_deep_research.utilities.url_utils import canonical_url_key

class ScopedPubMed(PubMedSearchEngine):
    # Controlled real-paper acceptance: actual PubMed retrieval, fixed document scope.
    def run(self,query,*args,**kwargs):
        return super().run(config["paper_scope"]+"[uid]",*args,**kwargs)

class CountedChat(ChatOpenAI):
    def invoke(self,*args,**kwargs):
        begun=time.monotonic()
        response=super().invoke(*args,**kwargs)
        CALLS.append({"elapsed_s":round(time.monotonic()-begun,3),
                      "usage":getattr(response,"usage_metadata",None)})
        return response

def progress(label):
    print("PROGRESS "+label,flush=True)

def metadata_summary(p):
    return {"status":p.status,"audit_status":p.audit_status,
            "audited_claims":len(p.citation_audit),"warnings":p.warnings,
            "sources":[source.model_dump() for source in p.sources],
            "content_sha256":p.content_sha256,"body_sha256":digest(p.report_body)}

def main():
    begun=time.monotonic()
    llm=CountedChat(model=config["model"],base_url=config["endpoint"],api_key=config["key"],
                   temperature=0,timeout=60,max_retries=0,max_tokens=2048)
    snapshot={"search.iterations":1,"search.questions_per_iteration":1,
              "search.tool":"pubmed","search.max_results":2,"search.cross_engine_filter":False,
              "report.enable_file_backup":True,"llm.model":config["model"],
              "llm.provider":"openai_endpoint","llm.temperature":0}
    settings=SimpleNamespace(username=None,get_setting=lambda key,default=None:snapshot.get(key,default))
    search_cls=ScopedPubMed if config.get("paper_scope") else PubMedSearchEngine
    search=search_cls(max_results=2,get_abstracts=True,get_full_text=False,
               llm=None if config.get("paper_scope") else llm,
               optimize_queries=not bool(config.get("paper_scope")),api_key=config.get("pubmed_key"),
               max_filtered_results=2,settings_snapshot=snapshot)
    system=AdvancedSearchSystem(llm=llm,search=search,strategy_name="source-based",
               max_iterations=1,questions_per_iteration=1,use_cross_engine_filter=False,
               settings_snapshot=snapshot,programmatic_mode=True)
    query=("Review the STEP 1 trial of once-weekly semaglutide in adults with overweight or obesity "
           "without diabetes (PMID 33567185). Focus on its population and body-weight result at week 68. "
           "Use exactly two short sections, with one subsection each, and at most three factual sentences "
           "per section. Cite each factual sentence. Distinguish findings from inference; do not give medical advice.")
    with settings_context(settings):
        progress("live PubMed source-based research")
        frozen=config.get("frozen_reports")
        if frozen:
            assert config.get("paper_scope")==frozen["paper_scope"]
            records=search.run(frozen["paper_scope"]+"[uid]")
            for index,record in enumerate(records,1): record["index"]=str(index)
            system.all_links_of_system.extend(records)
            results={"current_knowledge":frozen["quick"]}
        else:
            results=system.analyze_topic(query)
        sources=list(system.all_links_of_system)
        if not sources:
            raise RuntimeError("live_research_no_sources")
        raw=_extract_synthesized_answer(results)
        if not raw: raise RuntimeError("live_research_no_answer")
        progress("quick final publication")
        quick=publish_report(raw,sources,llm)
        validate_publication(quick.content,quick.metadata())
        assert quick.report_body==raw and quick.status=="unverified"
        progress("quick full report preserved; advisory checks="+str(len(quick.citation_audit)))
        if config.get("quick_only"):
            print("RESULT "+json.dumps({"checks_passed":True,"quick":metadata_summary(quick),
                "detailed":{"audited_claims":0},"elapsed_s":round(time.monotonic()-begun,3),
                "scope":"Quick report preservation only; no factual accuracy acceptance"}),flush=True)
            return
        progress("real detailed report generation")
        if frozen:
            detail_result={"content":frozen["detailed"],"metadata":{}}
        else:
            generator=IntegratedReportGenerator(search_system=system,settings_snapshot=snapshot,searches_per_section=1)
            detail_result=generator.generate_report(results,query)
        detail=publication_for_report(detail_result["content"],detail_result["metadata"],
                                       system.all_links_of_system,llm)
        validate_publication(detail.content,detail.metadata())
        assert detail.status=="unverified" and detail.report_body
        assert not any(label in detail.content for label in ("### 结论可溯源性核查", "### 待核验内容", "### 条件匹配核验", "### 关键词覆盖核验"))
        progress("detailed full report preserved; advisory checks="+str(len(detail.citation_audit)))
        progress("SQLite, file backup, display and exporters")
        engine=create_engine("sqlite:////data/publication-e2e.sqlite")
        Base.metadata.create_all(engine)
        storage_rows=[]
        backup=FileReportStorage(Path("/data/reports"))
        with Session(engine) as session:
            for mode,p in [("quick",quick),("detailed",detail)]:
                row=ResearchHistory(id=mode,query=query,mode=mode,status="completed",
                                    created_at=datetime.now(timezone.utc).isoformat(),research_meta={})
                session.add(row);session.commit()
                storage=DatabaseReportStorage(session)
                assert storage.save_report(mode,p.content,p.metadata())
                session.expire_all()
                row=session.query(ResearchHistory).filter_by(id=mode).one()
                assert row.report_content==p.content
                validate_publication(row.report_content,row.research_meta)
                assert storage.get_report(mode)==p.content
                assert backup.save_report(mode,p.content,p.metadata())
                assert backup.get_report(mode)==p.content
                validate_publication(backup.get_report(mode),backup.get_report_with_metadata(mode)["metadata"])
                assembled=assemble_full_report(row,session)
                assert assembled.startswith(p.content)
                exports={}
                for fmt in ("quarto","latex","odt","pdf","ris"):
                    data,name,mime=export_report_to_memory(assembled,fmt)
                    assert data or (fmt=="ris" and p.status=="withheld"), "empty_export_"+fmt
                    exports[fmt]={"bytes":len(data),"sha256":sha256(data).hexdigest(),"mimetype":mime}
                    if fmt=="quarto":
                        import io,zipfile
                        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                            qmd=next(n for n in bundle.namelist() if n.endswith(".qmd"))
                            import re
                            document=bundle.read(qmd).decode()
                            # Compare rendered prose: grouped references may become
                            # comma-separated links; Unicode reference brackets are
                            # also converted by the legacy Quarto exporter.
                            clean=lambda t: " ".join(re.sub(r"\[@[^\]]+\]|\[?[\[【]\d+(?:,\s*\d+)*[\]】]\]?(?:\([^)]*\))?", "", t).split())
                            expected, actual = clean(p.content), clean(document)
                            if expected not in actual:
                                from difflib import SequenceMatcher
                                match=SequenceMatcher(None,expected,actual,autojunk=False).find_longest_match()
                                raise AssertionError(f"quarto_prose_mismatch_{mode}_expected{len(expected)}_actual{len(actual)}_longest{match.size}")
                            bib=bundle.read("references.bib").decode()
                            # The native bibliography formatter canonicalizes URLs
                            # (e.g. a trailing slash); compare destinations, not spelling.
                            bib_urls={canonical_url_key(url) for url in re.findall(r"url = \{([^}]+)\}",bib)}
                            missing=[source.index for source in p.sources
                                     if source.url and canonical_url_key(source.url) not in bib_urls]
                            if missing: raise AssertionError(f"bib_missing_urls_{mode}_{missing}")
                            assert all(f"@misc{{ref{source.index}," in bib for source in p.sources)
                    if fmt=="ris":
                        records=data.decode()
                        assert records.count("ER  -")==len(p.sources)
                        ris_urls={canonical_url_key(line[6:]) for line in records.splitlines() if line.startswith("UR  - ")}
                        assert all(canonical_url_key(source.url) in ris_urls for source in p.sources if source.url)
                storage_rows.append({"mode":mode,"database_equal":True,"audit_roundtrip":True,
                    "chat_body_equal":row.report_content==p.content,"file_equal":True,
                    "display_prefix_equal":True,"exports":exports})
                assert storage.save_report(mode,p.content+" Unchecked assertion.",p.metadata()) is False
                session.refresh(row);assert row.report_content==p.content
        progress("disabled/offline/missing-source advice preserves reports")
        class Offline:
            def invoke(self,prompt): raise RuntimeError("offline")
        faults={}
        for label,model,cfg,records in [
            ("verification_disabled",llm,VerifyConfig(enable_verify=False),sources),
            ("model_offline",Offline(),VerifyConfig(),sources),
            ("sources_unavailable",llm,VerifyConfig(),[])]:
            p=publish_report(raw,records,model,cfg)
            assert p.status=="unverified" and p.report_body==raw
            validate_publication(p.content,p.metadata())
            faults[label]={"status":p.status,"audit_status":p.audit_status,"body_preserved":True}
        evidence_lookup={a.artifact_id:a for source in system.all_links_of_system for a in source_artifacts(source)}
        located=0
        for p in (quick,detail):
            for claim in p.citation_audit:
                for item in claim.citation_checks:
                    loc=item.evidence.locator if item.evidence else None
                    if loc:
                        assert evidence_lookup[loc.artifact_id].text[loc.start:loc.end]==loc.quote
                        located+=1
        result={"run_at_utc":datetime.now(timezone.utc).isoformat(),"model":config["model"],"temperature":0,
            "synthetic":False,"strategy":"source-based","search_engine":"PubMedSearchEngine",
            "search_iterations":0 if frozen else 1,"generation_mode":"frozen-generated-report-replay" if frozen else "live-strategy-and-generator","paper_scope":config.get("paper_scope"),"scope":"Report preservation and separate advisory metadata; actual strategy/generator plus SQLite/file/export. Not a factual accuracy acceptance.",
            "source_count":len(system.all_links_of_system),
            "source_artifacts":[{"paper_id":a.paper_id,"artifact_id":a.artifact_id,"basis":a.basis,
                                 "content_sha256":a.content_sha256} for s in system.all_links_of_system for a in source_artifacts(s)],
            "quick":metadata_summary(quick),"detailed":metadata_summary(detail),
            "storage_and_exports":storage_rows,"faults":faults,"located_advisory_quotes":located,
            "elapsed_s":round(time.monotonic()-begun,3),"model_calls":CALLS,
            "checks_passed":bool(quick.report_body==raw and detail.report_body and len(faults)==3)}
        # Persist hashes and summaries only; no source text or raw user content.
        print("RESULT "+json.dumps(result,ensure_ascii=False),flush=True)

try: main()
except Exception as exc:
    import traceback
    reason = str(exc) if str(exc) in {"live_research_no_sources","live_research_no_answer"} or str(exc).startswith(("quarto_prose_mismatch_","bib_missing_urls_")) else type(exc).__name__
    print("FAILURE "+json.dumps({"reason":reason,"frames":[{"file":Path(f.filename).name,"line":f.lineno}
          for f in traceback.extract_tb(exc.__traceback__)[-4:]]}),flush=True)
    raise SystemExit(1)
