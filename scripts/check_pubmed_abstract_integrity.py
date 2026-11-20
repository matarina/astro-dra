"""Compare the exact adapter method on frozen authoritative XML; no LLMs."""
import ast
import copy
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List
import xml.etree.ElementTree as ET


def parse_with_module(module, raw, ids):
    cls = next(n for n in ast.parse(module.read_text()).body
               if isinstance(n,ast.ClassDef) and n.name == "PubMedSearchEngine")
    method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name == "_get_article_abstracts")
    logger = SimpleNamespace(**{name:lambda *a,**k:None for name in ("debug","info","warning")})
    response = SimpleNamespace(text=raw,status_code=200,raise_for_status=lambda:None)
    ns = {"List":List,"Dict":Dict,"ET":ET,"logger":logger,
          "safe_get":lambda *a,**k:response,"_search_proxy_kwargs":lambda:{}}
    helpers = ast.parse((Path(__file__).resolve().parents[1] / "local_deep_research/research_verify/retrieval.py").read_text())
    ns.update(HTMLParser=HTMLParser,copy=copy)
    exec(compile(ast.Module(body=[n for n in helpers.body if isinstance(n,ast.FunctionDef)
                                and n.name in {"html_text","xml_text"}],type_ignores=[]),"native_markup_helpers","exec"),ns)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(module),"exec"),ns)
    obj = SimpleNamespace(api_key=None,rate_tracker=SimpleNamespace(apply_rate_limit=lambda *a:0),
                          engine_type="pubmed",fetch_url="frozen-xml",_scrub_error=lambda e:str(e))
    return ns["_get_article_abstracts"](obj,ids)


def main():
    root = Path("/data1/maxw/ldr-evaluation/pubmed-abstract-integrity-20261110")
    raw = (root / "efetch.xml").read_text()
    expected = {}
    nested = {}
    for article in ET.fromstring(raw).findall(".//PubmedArticle"):
        pmid = article.findtext("./MedlineCitation/PMID")
        nodes = article.findall("./MedlineCitation/Article/Abstract/AbstractText")
        parts = []
        for node in nodes:
            text = "".join(node.itertext()).strip()
            if text:parts.append((node.get("Label")+": " if node.get("Label") else "")+text)
        if parts:
            expected[pmid] = "\n\n".join(parts)
            nested[pmid] = any(len(node)>0 for node in nodes)
    arms = {"baseline":root / "baseline.py",
            "candidate":Path("local_deep_research/search_engine_pubmed.py")}
    result = {"scope":"exact primary abstract text reconstruction, not semantic/report efficacy",
              "raw_sha256":hashlib.sha256((root / "efetch.xml").read_bytes()).hexdigest(),
              "articles":len(expected),"nested_markup_articles":sum(nested.values()),"arms":{}}
    for arm,path in arms.items():
        got = parse_with_module(path,raw,list(expected))
        rows = [{"pmid":key,"matches_primary_abstract":got.get(key)==value,
                 "matches_after_whitespace_normalization":got.get(key,"").split()==value.split(),
                 "expected_chars":len(value),"actual_chars":len(got.get(key,"")),
                 "nested_markup":nested[key]} for key,value in expected.items()]
        result["arms"][arm] = {"matched":sum(r["matches_primary_abstract"] for r in rows),
                                "matched_after_whitespace_normalization":sum(r["matches_after_whitespace_normalization"] for r in rows),
                                "returned_ids":sorted(got),"rows":rows,
                                "module_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        (root / (arm + "-abstracts.json")).write_text(json.dumps(got,ensure_ascii=False,indent=2))
    Path("evaluation/pubmed-abstract-integrity-20261110.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__ == "__main__": main()
