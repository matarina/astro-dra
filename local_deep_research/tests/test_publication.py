"""Report preservation and actual storage/display boundaries after rule removal."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import pytest
from loguru import logger
from research_verify.publication import KEY, publish_report, publication_for_report, validate_publication
from research_verify.config import VerifyConfig

ROOT = Path(__file__).parents[2]
QUOTE = "In cultured cells, M regulates proliferation."
BODY = "# Findings\n\nIn cultured cells, M regulates proliferation [7].\n\nUncited clinical benefit."

def source(index=7):
    return {"index":index, "doi":"10.1234/test", "abstract":QUOTE,
            "title":"Fixture source", "link":"https://doi.org/10.1234/test"}

class Judge:
    def __init__(self, verdict="supported", quote=QUOTE):
        self.calls = 0
        self.verdict, self.quote = verdict, quote
    def invoke(self, prompt):
        self.calls += 1
        return SimpleNamespace(content=json.dumps({"verdict":self.verdict,
            "supporting_fragment":self.quote, "reason":"fixture"}))

def published(model=None):
    return publish_report(BODY, [source()], model)

@pytest.mark.parametrize("verdict", ["supported", "partial", "unsupported", "unverifiable"])
def test_every_advisory_verdict_preserves_all_report_content(verdict):
    model = Judge(verdict)
    p = published(model)
    assert p.status == "unverified" and p.report_body == BODY
    assert "Uncited clinical benefit." in p.content
    assert "# Findings" in p.content
    assert "[[1]](https://doi.org/10.1234/test)" in p.content
    assert model.calls == 1  # No rewrite, final recheck, or audit of uncited prose.
    assert len(p.citation_audit) == 1 and p.audit_status == "completed"
    assert all(word not in p.content for word in ["核验", "待核验", "缺少支撑"])
    assert validate_publication(p.content, p.metadata()) == p

def test_missing_source_text_or_unresolved_reference_never_drops_a_sentence():
    p = publish_report("A [7]. B [99]. Uncited C.", [source() | {"abstract":""}], Judge())
    assert p.report_body == "A [7]. B [99]. Uncited C."
    assert "B [99]. Uncited C." in p.content
    assert p.warnings == ["unresolved_citation:99"]
    assert p.citation_audit[0].verdict == "unverifiable"
    validate_publication(p.content,p.metadata())

@pytest.mark.parametrize("model", [None, Judge(quote="Fabricated quote.")])
def test_no_judge_or_fabricated_evidence_does_not_block_the_report(model):
    p = published(model)
    assert p.report_body == BODY and "Uncited clinical benefit." in p.content
    assert p.status == "unverified"
    if model:
        assert p.citation_audit[0].verdict == "unverifiable"

def test_disabled_or_throwing_audit_preserves_text_without_certifying_it():
    class Offline:
        def invoke(self, prompt): raise RuntimeError("offline")
    p = published(Offline())
    assert p.audit_status == "unavailable" and p.report_body == BODY
    p = publish_report(BODY, [source()], Judge(), VerifyConfig(enable_verify=False))
    assert p.audit_status == "disabled" and p.report_body == BODY
    assert not p.citation_audit and p.status == "unverified"

def test_no_citations_retains_the_entire_report():
    p = publish_report("# Answer\n\nUseful contextual discussion.", [], Judge())
    assert p.content == p.report_body
    assert p.audit_status == "no_cited_claims"

def test_ambiguous_source_index_stays_unlinked_instead_of_guessing():
    p = publish_report("A [7].", [source(), source() | {"doi":"10.1234/other"}], Judge())
    assert p.content == "A [7]." and not p.sources
    assert p.warnings == ["unresolved_citation:7"]

def test_same_paper_has_one_number_in_first_appearance_order():
    p = publish_report("A [9]. B [7].", [source(), source(9)], None)
    assert [s.index for s in p.sources] == [1]
    assert p.sources[0].original_indices == [9,7]
    validate_publication(p.content,p.metadata())

@pytest.mark.parametrize("mutation", ["content", "body", "status", "url", "indices"])
def test_serialization_checks_do_not_turn_into_semantic_gates(mutation):
    p = published(); m = deepcopy(p.metadata()); d = m[KEY]
    if mutation == "content": d["content"] += " changed"
    elif mutation == "body": d["report_body"] += " changed"
    elif mutation == "status": d["status"] = "traceability_checked"
    elif mutation == "url": d["sources"][0]["url"] = "javascript:alert(1)"
    elif mutation == "indices": d["sources"].append(d["sources"][0])
    with pytest.raises(ValueError): validate_publication(p.content,m)

def test_detailed_publication_reuse_does_not_repeat_the_audit():
    model=Judge(); p=published(model)
    assert publication_for_report(p.content,p.metadata(),[source()],model)==p
    assert model.calls==1
    changed=publication_for_report(p.content+" New discussion.",p.metadata(),[source()],None)
    assert "New discussion." in changed.content and changed.status=="unverified"

def load_boundary(relative,class_name,method):
    tree=ast.parse((ROOT/"local_deep_research"/relative).read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method)
    ns={"Dict":dict,"Any":object,"Optional":__import__("typing").Optional,"logger":logger,
        "ResearchHistory":object}
    exec(compile(ast.Module(body=[node],type_ignores=[]),relative,"exec"),ns)
    return ns[method]

@pytest.mark.parametrize("metadata", [{}, None, {"legacy":True}])
def test_database_accepts_ordinary_reports_without_a_verification_certificate(metadata):
    save=load_boundary("overlay/database_storage.py","DatabaseReportStorage","save_report")
    row=SimpleNamespace(report_content=None,research_meta={})
    query=SimpleNamespace(filter_by=lambda **kw:SimpleNamespace(first=lambda:row))
    session=SimpleNamespace(query=lambda *args:query,commit=lambda:None,rollback=lambda:None)
    assert save(SimpleNamespace(session=session),"id",BODY,metadata,None)
    assert row.report_content==BODY

def test_database_persists_failed_advice_and_full_body():
    save=load_boundary("overlay/database_storage.py","DatabaseReportStorage","save_report")
    row=SimpleNamespace(report_content=None,research_meta={})
    query=SimpleNamespace(filter_by=lambda **kw:SimpleNamespace(first=lambda:row))
    session=SimpleNamespace(query=lambda *args:query,commit=lambda:None,rollback=lambda:None)
    p=published(Judge("unsupported"))
    assert save(SimpleNamespace(session=session),"id",p.content,p.metadata(),None)
    assert row.report_content==p.content
    assert row.research_meta[KEY]["citation_audit"][0]["verdict"]=="unsupported"

def test_assembler_displays_answer_and_sources_without_audit_tables():
    tree=ast.parse((ROOT/"local_deep_research/overlay/report_assembly_service.py").read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assemble_full_report")
    ns={"Optional":__import__("typing").Optional,"ResearchHistory":object,"Session":object,
        "_build_metrics_markdown":lambda r:"", "_LEGACY_SOURCES_RE":re.compile(r"^## Sources",re.M)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"assemble","exec"),ns)
    p=published(Judge("unsupported")); row=SimpleNamespace(report_content=p.content,research_meta=p.metadata())
    result=ns["assemble_full_report"](row,None)
    assert result.startswith(p.content) and "[1] Fixture source" in result
    assert "核验" not in result and "Uncited clinical benefit." in result
    row.report_content+=" More discussion."
    assert ns["assemble_full_report"](row,None)==row.report_content

def test_actual_detailed_generator_preserves_unverified_content():
    tree=ast.parse((ROOT/"local_deep_research/overlay/report_generator.py").read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="IntegratedReportGenerator")
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="generate_report")
    ns={"Dict":dict}; exec(compile(ast.Module(body=[node],type_ignores=[]),"generator","exec"),ns)
    obj=SimpleNamespace(_determine_report_structure=lambda *a:[],
        _research_and_generate_sections=lambda *a,**k:[],
        _format_final_report=lambda *a:{"content":BODY,"metadata":{}},model=Judge("unsupported"),
        search_system=SimpleNamespace(all_links_of_system=[source()]))
    result=ns["generate_report"](obj,{},"query")
    p=validate_publication(result["content"],result["metadata"])
    assert p.report_body==BODY and p.status=="unverified"

@pytest.mark.parametrize("citation", ["[7](https://example.com/paper)", "[[7]](https://example.com/paper)"])
def test_quarto_wrapper_normalizes_numeric_hyperlinks_only(citation):
    import io,zipfile
    from local_deep_research.exporters.quarto_exporter import QuartoExporter
    body = f"Fact {citation}. See [website](https://example.com).\n\n## Sources\n\n[7] Paper\n   URL: https://example.com/paper"
    result = QuartoExporter().export(body)
    with zipfile.ZipFile(io.BytesIO(result.content)) as bundle:
        text = bundle.read(next(n for n in bundle.namelist() if n.endswith(".qmd"))).decode()
        bib = bundle.read("references.bib").decode()
    assert "Fact [@ref7]." in text and "[website](https://example.com)" in text
    assert "https://example.com/paper" in bib



def test_bibliography_uses_display_numbers_and_code_is_unchanged():
    bibliography="## Sources\n\n[7, 9] Shared article\n   URL: https://doi.org/10.1234/test"
    body="A [7, 9].\n\n```\nExample [7].\n```\n\n"+bibliography
    p=publish_report(body,[source(),source(9)],None)
    assert "A [[1]](https://doi.org/10.1234/test)." in p.content
    assert "Example [7]." in p.content
    assert "[1] Shared article" in p.content and "[7, 9] Shared article" not in p.content
    assert p.sources[0].title=="Fixture source" and p.sources[0].original_indices==[7,9]
    validate_publication(p.content,p.metadata())


def test_distinct_papers_are_numbered_by_first_use_and_repeated_consistently():
    a=source(9)
    b=source(7) | {"doi":"10.1234/b", "link":"https://doi.org/10.1234/b", "title":"Article B"}
    p=publish_report("First [9]. Second [7]. Again [9, 7].",[b,a],None)
    assert [s.index for s in p.sources]==[1,2]
    assert [s.original_indices for s in p.sources]==[[9],[7]]
    assert p.content==("First [[1]](https://doi.org/10.1234/test). "
        "Second [[2]](https://doi.org/10.1234/b). "
        "Again [[1]](https://doi.org/10.1234/test), [[2]](https://doi.org/10.1234/b).")
    validate_publication(p.content,p.metadata())


@pytest.mark.parametrize("marker", ["[7]", "[7](https://old.example)", "[[7]](https://old.example)", "【7】"])
def test_numeric_citation_input_styles_share_one_display_format(marker):
    p=publish_report(f"Statement {marker}.",[source()],None)
    assert p.content=="Statement [[1]](https://doi.org/10.1234/test)."
    validate_publication(p.content,p.metadata())


def test_unresolved_citation_number_is_never_reused_for_a_different_source():
    p=publish_report("Known [9]. Missing [1].",[source(9)],None)
    assert p.content=="Known [[2]](https://doi.org/10.1234/test). Missing [1]."
    assert p.sources[0].index==2
    validate_publication(p.content,p.metadata())


def test_reference_order_does_not_determine_the_body_numbering():
    a=source(9)
    b=source(7) | {"doi":"10.1234/b", "link":"https://doi.org/10.1234/b", "title":"Article B"}
    body="First [9]. Second [7].\n\n## Sources\n\n[7] Article B\n[9] Article A\n\n## Discussion\nOther discussion."
    p=publish_report(body,[b,a],None)
    assert "First [[1]]" in p.content and "Second [[2]]" in p.content
    assert "[2] Article B" in p.content and "[1] Article A" in p.content
    assert [s.original_indices for s in p.sources]==[[9],[7]]
    assert "## Discussion\nOther discussion." in p.content
    assert p.report_body==body
    validate_publication(p.content,p.metadata())


def test_original_audit_positions_and_reference_numbers_survive_display_compaction():
    model=Judge()
    p=publish_report("In cultured cells, M regulates proliferation [9].",[source(9)],model)
    assert p.citation_audit[0].citations==[9]
    assert p.sources[0].original_indices==[9] and p.sources[0].index==1
    assert p.report_body[p.citation_audit[0].report_start:p.citation_audit[0].report_end]==p.citation_audit[0].claim
    assert "[[1]]" in p.content and model.calls==1


def test_old_advisory_report_can_be_formatted_for_view_without_database_changes():
    from research_verify.publication import Publication, PublishedSource, _render_report_v2, digest, presentation_for_publication
    body="Statement [9]. Again [9]."
    sources=[PublishedSource(index=9,original_indices=[9],paper_id="doi:10.1234/test",artifact_id="",title="Fixture source",url="https://doi.org/10.1234/test")]
    content=_render_report_v2(body,sources)
    old=Publication(schema_version="2.0",status="unverified",content=content,
                    content_sha256=digest(content),report_body=body,sources=sources)
    saved=old.model_dump_json()
    validate_publication(content,old.metadata())
    view=presentation_for_publication(old)
    assert view.schema_version=="2.1" and "[[1]]" in view.content
    assert view.sources[0].paper_id=="doi:10.1234/test"
    assert old.model_dump_json()==saved
    validate_publication(view.content,view.metadata())


@pytest.mark.parametrize("heading", ["## Sources:", "## 参考文献：", "## 引用文献"])
def test_reference_heading_variants_are_rebuilt_without_counting_unused_entries(heading):
    body="A [9].\n\n"+heading+"\n\n[3] Unused entry\n[9] Fixture A\n\n### Discussion\nKeep this explanation."
    p=publish_report(body,[source(9),source(3)|{"doi":"10.1234/b"}],None)
    assert len(p.sources)==1 and p.sources[0].original_indices==[9]
    assert "[1] Fixture A" in p.content and "[3] Unused entry" in p.content
    assert p.sources[0].title=="Fixture source" and p.report_body==body
    assert "### Discussion\nKeep this explanation." in p.content
    validate_publication(p.content,p.metadata())


def test_reference_headings_inside_code_are_preserved():
    code="```markdown\n## Sources\n[7] Example reference\n```"
    body="Fact [9].\n\n"+code
    p=publish_report(body,[source(9)],None)
    assert p.content.endswith(code) and len(p.sources)==1
