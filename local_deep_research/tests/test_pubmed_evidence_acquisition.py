"""Original PubMed evidence acquisition regressions."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
import json
import pytest
from research_verify.citation_qc import CitationQc
from research_verify.publication import SourceCollector
from research_verify.semantics import DIMENSIONS

ROOT=Path(__file__).parents[2]
QUOTE="In cultured cells, M regulates proliferation."

def test_raw_abstract_preferred_over_enriched_metadata():
    class Judge:
        def invoke(self,prompt):
            return SimpleNamespace(content=json.dumps({"verdict":"supported","supporting_fragment":QUOTE,"reason":"fixture",
                "dimensions":{n:{"status":"matched","evidence_quote":QUOTE,"reason":"fixture"} for n in DIMENSIONS}}))
    record={"index":7,"doi":"10.1234/test","abstract":QUOTE,
            "full_content":QUOTE+" Engine-added journal rank: 100.","content_type":"abstract"}
    qc=CitationQc(Judge())
    check=qc.check(qc.extract_claims("In cultured cells, M regulates proliferation [7]."),
                   SourceCollector([record]))[0]
    assert check.verdict=="supported"
    assert check.citation_checks[0].source_field=="abstract"
    assert check.citation_checks[0].assessed_chars==len(QUOTE)

@pytest.mark.parametrize("options,expected",[
    ({},False),({"get_abstracts":False},True),
    ({"search_snippets_only":True},True),
    ({"get_abstracts":False,"get_full_text":True},False)])
def test_pubmed_constructor_respects_original_content_request(options,expected):
    tree=ast.parse((ROOT/"local_deep_research/search_engine_pubmed.py").read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="PubMedSearchEngine")
    node=deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="__init__"))
    start=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
               and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=="__init__")
    node.body=ast.parse("preview_filters=[]").body+node.body[start:]
    cls=ast.ClassDef(name="Engine",bases=[ast.Name(id="Base",ctx=ast.Load())],
                    keywords=[],body=[node],decorator_list=[])
    class Base:
        def __init__(self,**kwargs):
            self.max_results=kwargs["max_results"]
            self.search_snippets_only=kwargs["search_snippets_only"]
    ns={"Base":Base,"Optional":Optional,"Dict":dict,"Any":Any,"BaseLLM":object}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),
                 "pubmed-initialization","exec"),ns)
    assert ns["Engine"](**options).search_snippets_only is expected
