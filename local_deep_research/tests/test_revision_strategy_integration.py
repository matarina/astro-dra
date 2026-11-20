"""Actual strategy finalize entry with isolated application dependencies."""
import ast
import hashlib
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
from typing import Any

from loguru import logger

from research_verify.semantics import DIMENSIONS


def runner_for(body, model):
    tree=ast.parse((Path(__file__).parents[1]/"langgraph_agent_strategy.py").read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="LangGraphAgentStrategy")
    methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in {"_finalize", "_attach_citation_qc"}]
    collector_node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="SearchResultsCollector")
    ns={"hashlib":hashlib,"json":json,"re":re,"threading":threading,"logger":logger,"DEFAULT_MAX_UNIQUE_SOURCES":80,
        "Dict":dict,"Any":Any,"NO_RESULTS_MESSAGE":"NO_RESULTS"}
    exec(compile(ast.Module(body=[collector_node,*methods],type_ignores=[]),"<actual-finalize>","exec"),ns)
    quote="In cultured cells, M regulates proliferation."
    source={"index":"1","doi":"10.1234/fixture","full_content":quote,"content_type":"full_text"}
    collector=ns["SearchResultsCollector"]([source])
    collector._results=[source]
    runner=SimpleNamespace(
        model=model,collector=collector,all_links_of_system=[source],
        _attach_doi_verification=lambda sources:None,
        _attach_constraint_match=lambda query,sources:False,
        _attach_keyword_coverage=lambda query,sources:None,
        _update_progress=lambda *args:None,
        get_setting=lambda key, default=None: default,
        citation_handler=SimpleNamespace(analyze_followup=lambda *args,**kwargs:{"content":body}),
        _format_citations=lambda answer,sources:answer+"\n\n## Sources\n1. fixture",
        _render_constraint_section=lambda sources:"",
        _render_keyword_section=lambda sources:"",
        _render_verify_section=lambda sources:"",
        _write_citation_qc_json=lambda checks:None,
    )
    runner._attach_citation_qc = lambda *args: ns["_attach_citation_qc"](runner, *args)
    return ns["_finalize"],runner,quote


class Supported:
    def invoke(self,prompt):
        quote="In cultured cells, M regulates proliferation."
        return SimpleNamespace(content=json.dumps({
            "verdict":"supported","supporting_fragment":quote,"reason":"fixture",
            "dimensions":{name:{"status":"matched","evidence_quote":quote,"reason":"fixture"}
                          for name in DIMENSIONS}}))


def test_finalize_preserves_full_generated_report_without_rule_tables():
    body="In cultured cells, M regulates proliferation [1]. Uncited clinical benefit."
    finalize,runner,_=runner_for(body,Supported())
    result=finalize(runner,"query",body,1,1,[])
    assert result["findings"][0]["content"]==body
    assert result["current_knowledge"]==body
    assert "Uncited clinical benefit." in result["formatted_findings"]
    assert "核验" not in result["formatted_findings"]
    assert "citation_revision" not in result


def test_finalize_does_not_call_a_verifier_or_suppress_content_on_outage():
    class Offline:
        def invoke(self,prompt): raise AssertionError("Finalization must not call the model")
    body="Unverified statement [1]."
    finalize,runner,_=runner_for(body,Offline())
    result=finalize(runner,"query",body,1,1,[])
    assert result["findings"][0]["content"]==body
    assert result["current_knowledge"]==body
