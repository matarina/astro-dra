import hashlib
import json
from types import SimpleNamespace

import pytest

from research_verify.evidence_flow import parse_review
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.generation import format_source_documents
from research_verify.semantic_evidence import semantic_passages
from research_verify.task_evidence import plan_evidence_gaps, task_coverage
from research_verify.task_eligibility import (
    assess_eligibility, carry_eligibility_quotes, eligibility_lists, missing_supporting_quotes,
)
from research_verify.task_plan import compile_search, validate_task_plan


def test_semantic_passages_keep_original_locations_for_writer_and_review():
    specific = "Methods: molecular imaging distinguished 8 exposed and 6 control samples."
    secondary = "Appendix 2. The response cohort had 4 positive and 1 negative sample."
    noise = "\n\n".join("Introduction and prior work in the field. " * 40 for _ in range(14))
    body = noise + "\n\n" + specific + "\n\n" + secondary + "\n\nReferences\n\n" + noise

    def invoke(prompt):
        windows = json.loads(prompt.split("Source windows:\n", 1)[1])
        assert "References" not in windows.values()
        return json.dumps({"selected_source_ids": [int(i) for i, chunk in windows.items()
                                                   if specific in chunk or secondary in chunk]})

    passages, status = semantic_passages(body, "Group sizes by assay?", invoke)
    assert status == "screened"
    for item in passages:
        assert body[item["start"]:item["end"]] == item["text"]
        assert hashlib.sha256(item["text"].encode()).hexdigest() == item["sha256"]
    records = [dict(item, url="https://example.org/article") for item in passages]
    doc = SimpleNamespace(page_content=body, metadata={"index": 1, "abstract": "The abstract.",
                                                        "_evidence_passages": records})
    writer = format_source_documents([doc], "Broad topic")
    reviewer = format_source_documents([doc], "Different formulation")
    for rendered in (writer, reviewer):
        assert specific in rendered and secondary in rendered
        assert rendered.views[1]["evidence_passages"] == records


def test_large_prechecked_papers_leave_room_for_new_and_later_sources():
    from research_verify.jcr_adapter import sources_with_journal_receipts

    documents = []
    for index in range(1, 6):
        abstract = f"Original abstract for paper {index}."
        metadata = {"index": index, "title": f"Paper {index}", "abstract": abstract}
        if index < 5:
            metadata["_screened_task"] = True
            metadata["_evidence_passages"] = [
                {"url": "https://example.org/article", "start": n * 2400, "end": (n + 1) * 2400,
                 "text": f"Original passage {n} for paper {index}. ".ljust(2400, "x")}
                for n in range(5)
            ]
        documents.append(SimpleNamespace(page_content=abstract, metadata=metadata))

    material = format_source_documents(
        documents, "Study methods?", max_chars=14_000,
        selector=lambda _: '{"selected_source_ids":[5]}',
    )
    assert set(material.views) == {1, 2, 3, 4, 5}
    assert len(material) <= 14_000
    for doc in documents[:-1]:
        index = doc.metadata["index"]
        original = doc.metadata["_evidence_passages"][0]
        assert material.views[index]["evidence_passages"] == [original]
        assert original["text"] in material

    documents[0].metadata.update(impact_factor=7.9, metric_year=2025, passes_threshold=False)
    scoped = sources_with_journal_receipts([doc.metadata for doc in documents], {}, {})
    for doc, metadata in zip(documents, scoped):
        doc.metadata = metadata
    with_legacy_flag = format_source_documents(
        documents, "Study methods?", max_chars=14_000,
        selector=lambda _: '{"selected_source_ids":[5]}',
    )
    assert with_legacy_flag == material
    assert with_legacy_flag.views == material.views


def test_reread_planner_sees_later_candidates_within_its_budget(monkeypatch):
    from research_verify import task_evidence

    sources = [{"index": i, "title": f"Teaching study {i}", "doi": f"10.1234/lesson{i}",
                "abstract": "Beginning of abstract. " + "Details. " * 200 + "Independent cohort data.",
                "_screened_task": True} for i in range(1, 101)]
    sources[-1]["_jcr_check"] = {"passes_threshold": False}
    plan = {"questions": [{"question": "How large were the groups?"}]}

    def invoke(prompt, **kwargs):
        previews = prompt.rsplit("Sources:\n", 1)[-1]
        assert len(previews) <= 42_000
        assert "[1] Teaching study 1" in previews and "[100] Teaching study 100" in previews
        assert "Independent cohort data." in previews
        return '{"gaps":[{"source_id":100,"question":"Methods group sizes"}]}'

    targets = []
    monkeypatch.setattr(task_evidence, "gather_evidence",
                        lambda handler, sources, requested, *args: targets.extend(requested) or True)
    trace = SimpleNamespace(record=lambda *args: None)
    assert plan_evidence_gaps(SimpleNamespace(_invoke_text=invoke), plan, sources, "", trace)
    assert targets == [(100, "Methods group sizes")]


@pytest.mark.parametrize("report", [
    "The reading intervention enrolled 26 pupils. The comparison group enrolled 20 pupils [7].",
    "- Reading intervention: 26 pupils.\n- Comparison group: 20 pupils [7].",
    "| Reading intervention | Comparison group |\n|---|---|\n| 26 pupils | 20 pupils [7] |",
])
def test_independent_education_study_checks_work_across_report_formats(report):
    quote = "The reading intervention enrolled 26 pupils."
    claim = {"text": report, "source_ids": [7]}
    response = {"issues": [{"claim_id": 1, "status": "supported", "source_id": 7,
                            "evidence_quote": quote, "atom_checks": [
        {"assertion": "26 pupils", "attribute": "quantity", "claim_value": 26,
         "source_id": 7, "result": "supported", "evidence_quote": quote},
        {"assertion": "20 pupils", "attribute": "quantity", "claim_value": 20,
         "source_id": 7, "result": "not_reported"},
    ]}]}
    issues, checked = parse_review(json.dumps(response), {1: claim}, include_checked=True, material={7: quote})
    assert issues[0]["status"] == "insufficient_evidence" and not checked
    assert [atom["result"] for atom in issues[0]["atom_checks"]] == ["supported", "not_reported"]

    plan = {"questions": [{"question": "How many pupils enrolled in each group?"},
                          {"question": "Which reading assessment was used?"}]}
    def invoke(prompt, *, trace, stage):
        if stage == "task_coverage":
            return json.dumps({"questions": [
                {"question": plan["questions"][0]["question"], "status": "answered", "report_quotes": quotes},
                {"question": plan["questions"][1]["question"], "status": "missing", "report_quotes": []},
            ]})
        return json.dumps({"questions": [
            {"id": 1, "status": "answered", "reviewed_scope": "Enrollment in both groups", "quote_ids": [1, 2]},
            {"id": 2, "status": "missing", "reviewed_scope": "No reading assessment in the report",
             "open_scope": "Identify the reading assessment"},
        ]})

    quotes = ["26 pupils", "20 pupils"]
    handler = SimpleNamespace(_invoke_text=invoke)
    trace = SimpleNamespace(record=lambda *args: None)
    status = task_coverage(handler, plan, report, trace)
    assert [item["status"] for item in status.values()] == ["answered", "missing"]
    assert status[1]["report_quotes"] == quotes
    quotes = ["26 pupils. 20 pupils"]
    assert task_coverage(handler, plan, report, trace)[1]["status"] == "unchecked"


@pytest.mark.parametrize(("quote_ids", "source_ids", "expected"), [
    ([1], [4], "partial"), ([1, 2], [4], "unchecked"), ([1], [4, 8], "unchecked"),
])
def test_mixed_report_quotes_preserve_usable_evidence_and_scope(quote_ids, source_ids, expected):
    first = "The Meridian archive used a six-month review cycle [4]."
    second = "The Oak archive gave no confirmed review interval [8]."
    invalid = "The Oak archive used a twelve-month review cycle [8]."
    report = f"{first}\n\n{second}"
    request = "Compare the review intervals across the archives."
    plan = {"questions": [{"question": "Compare review intervals."}]}

    def invoke(prompt, *, trace, stage):
        assert request in prompt
        if stage == "task_coverage":
            return json.dumps({"questions": [
                {"question": "What interval did Meridian use?", "status": "answered", "report_quotes": [first]},
                {"question": "What intervals did the archives use?", "status": "answered",
                 "report_quotes": [first, invalid]},
            ]})
        assert stage == "task_coverage_scope"
        evidence, context = prompt.split("Located passages and questions: ", 1)[1].split("\nOriginal user request:", 1)
        assert first in evidence and invalid not in evidence and second in context
        return json.dumps({"questions": [
            {"id": 1, "status": "answered", "reviewed_scope": "Meridian's schedule", "quote_ids": [1]},
            {"id": 2, "status": "partial", "reviewed_scope": "Meridian's schedule",
             "open_scope": "Determine Oak's interval", "quote_ids": quote_ids, "source_ids": source_ids},
        ]})

    trace = SimpleNamespace(record=lambda *args: None)
    result = task_coverage(SimpleNamespace(_invoke_text=invoke), plan, report, trace, user_request=request)
    assert [item["status"] for item in result.values()] == ["answered", expected]
    assert result[2]["reported_status"] == "answered" and result[2]["source_ids"] == [4]
    assert result[2]["quote_ids"] == [1] and result[2]["report_quotes"] == [first]
    assert result[2]["quote_checks"] == [
        {"quote": first, "status": "matched", "start": 0, "end": len(first), "source_ids": [4]},
        {"quote": invalid, "status": "not_found"},
    ]
    if expected == "partial":
        assert result[2]["reviewed_scope"] == "Meridian's schedule"
        assert result[2]["open_scope"] == "Determine Oak's interval"


@pytest.mark.parametrize(("report", "status", "open_scope"), [
    ("Both the Delta and Valley standards require annual inspection filed with the local authority [1, 2].",
     "answered", ""),
    ("Both the Delta and Valley standards require annual inspection [1, 2].",
     "partial", "Who receives the inspection results"),
])
def test_model_decides_coverage_using_request_scope_instead_of_number_of_sources(report, status, open_scope):
    request = "Summarize the standards' inspection interval and where the results go."
    plan = {"questions": [{"question": "What is the interval?"}, {"question": "Where do the results go?"}]}
    replies = iter([
        {"questions": [{"question": "Summarize inspection requirements", "status": "answered",
                        "report_quotes": [report]}]},
        {"questions": [{"id": 1, "status": status, "reviewed_scope": "Requirements stated for both standards",
                        "open_scope": open_scope, "quote_ids": [1], "source_ids": [1, 2]}]},
    ])

    def invoke(prompt, *, trace, stage):
        assert request in prompt and report in prompt
        return json.dumps(next(replies))

    result = task_coverage(SimpleNamespace(_invoke_text=invoke), plan, report,
                           SimpleNamespace(record=lambda *a: None), user_request=request)
    assert len(result) == 1 and result[1]["status"] == status
    assert result[1]["source_ids"] == [1, 2]
    assert result[1].get("open_scope", "") == open_scope


def test_task_plan_separates_report_year_and_compiles_each_database():
    query = "Search 2020–2026 for imaging [pilot cohort]. Report only 2026 studies."
    plan = validate_task_plan(query, {
        "concepts": [["imaging", "image analysis"]],
        "publication_years": {"start": 2020, "end": 2026, "user_quote": "2020–2026"},
        "report_publication_years": {"start": 2026, "end": 2026, "user_quote": "only 2026 studies"},
        "native_search": {"engine": "pubmed", "query": "invented[Title]"},
    })
    assert plan["report_publication_years"]["start"] == 2026
    assert "native_search" not in plan
    pm = compile_search("pubmed", "", None, plan)
    epmc = compile_search("europepmc", "", None, plan)
    assert '"imaging"[Title/Abstract]' in pm and "2020[dp]:2026[dp]" in pm
    assert '"imaging"' in epmc and "FIRST_PDATE:[2020-01-01 TO 2026-12-31]" in epmc
    assert "pilot cohort" not in pm + epmc


def test_europepmc_pmid_resolves_to_pmc_before_xml_fetch():
    client = EvidenceFetcher(get=lambda *args, **kw: None)
    urls = []
    client.record = lambda source: {"pmid": "123", "pmcid": "PMC456", "doi": "10.1000/xyz"}

    def read(url, **kwargs):
        urls.append(url)
        return """<article><front><article-meta>
        <article-id pub-id-type="pmid">123</article-id>
        <article-id pub-id-type="pmc">456</article-id>
        <article-id pub-id-type="doi">10.1000/xyz</article-id>
        </article-meta></front><body><sec><title>Methods</title>
        <p>Both workflows used 12 samples.</p></sec></body></article>"""

    client.read = read
    result = client.source_article({"pmid": "123"})
    assert "Both workflows used 12 samples." in result["body"]
    assert len(urls) == 1 and urls[0].endswith("/PMC456/fullTextXML")


def test_wrong_publisher_identity_never_attaches_body():
    client = EvidenceFetcher(get=lambda *args, **kw: None)
    client.record = lambda source: {}
    client.read = lambda url, **kwargs: '<meta name="citation_doi" content="10.1000/wrong"><p>Different paper.</p>'
    assert client.source_article({"doi": "10.1000/right"}) is None
    assert client.events[-1]["status"] == "identity_mismatch"


def test_eligibility_does_not_count_pending_or_confirmed_below_threshold():
    sources = [{"index": 1, "pubdate": "2026", "_jcr_check": {"status": "found", "impact_factor": 18.1,
                                                             "requested_metric_year": "latest"}},
               {"index": 2, "pubdate": "2026", "_jcr_check": {"status": "found", "impact_factor": 7.9,
                                                             "passes_threshold": True,
                                                             "requested_metric_year": "latest"}},
               {"index": 3, "pubdate": "2026"}]
    docs = [SimpleNamespace(metadata={"index": i}, page_content="Primary study reports a new experiment.")
            for i in range(1, 4)]
    criteria = {"publication_years": {"start": 2026, "end": 2026},
                "eligibility": [{"criterion": "Original research"}]}
    selection = {"year": "latest", "minimum": 10, "operator": ">"}

    def invoke(prompt, **kwargs):
        assert "IF at least 10" not in prompt
        return json.dumps({"checks": [{"source_id": i, "criterion_id": 1, "status": "supported",
                                       "quote": "Primary study reports a new experiment."} for i in (1, 2, 3)]})

    trace = SimpleNamespace(record=lambda *args: None)
    ledger = assess_eligibility(SimpleNamespace(_invoke_text=invoke), criteria, docs, sources, trace,
                                {1, 2, 3}, journal_selection=selection)
    assert eligibility_lists(ledger, sources) == ([1], [3])
    assert ledger[2]["status"] == "excluded"


def test_joint_eligibility_accepts_separate_original_spans_from_the_same_source():
    source = {"index": 7, "pubdate": "2026"}
    first = "We recorded interviews from both schools."
    second = "The same study compared test scores."
    document = SimpleNamespace(metadata={"index": 7}, page_content=f"{first}\n\nMethods appendix.\n\n{second}")
    plan = {"eligibility": [{"criterion": "Uses interviews and test scores"}]}
    trace = SimpleNamespace(record=lambda *args: None)

    def evaluate(quotes):
        handler = SimpleNamespace(_invoke_text=lambda *args, **kw: json.dumps({
            "checks": [{"source_id": 7, "criterion_id": 1, "status": "supported", "quotes": quotes}]
        }))
        return assess_eligibility(handler, plan, [document], [source], trace, {7})

    verified = evaluate([first, second])
    assert verified[7]["status"] == "confirmed"
    assert [row["quote"] for row in missing_supporting_quotes(verified, [7], {})] == [first, second]
    assert evaluate([first + " " + second])[7]["status"] == "pending"
    assert evaluate([first, "A quote from a different study."])[7]["status"] == "pending"


def test_write_notes_retain_only_the_missing_verified_eligibility_quotes():
    quote = "Spatial transcriptomics was performed using a Xenium panel."
    record = {"status": "supported", "quote": quote, "source_block_start": 4835}
    ledger = {4: {"criteria": {1: {"status": "unsupported"}, 2: record, 3: record}},
              5: {"criteria": {2: record}}}
    views = {4: {"block": "The abstract describes the study."}, 5: {"block": quote}}
    assert missing_supporting_quotes(ledger, [4, 5], views) == [
        {"source_id": 4, "quote": quote, "source_block_start": 4835}
    ]
    material = format_source_documents([
        SimpleNamespace(page_content=views[4]["block"], metadata={"index": 4, "title": "Study"}),
    ])
    with_evidence = carry_eligibility_quotes(material, missing_supporting_quotes(ledger, [4], material.views))
    assert quote in with_evidence and quote in with_evidence.views[4]["text"]
    assert with_evidence.views[4]["block"] in with_evidence



def test_journal_fields_are_not_required_or_interpreted_as_task_plan_fields():
    prompt = "影响因 子10分以上，只要2 026年的文章"
    plan = validate_task_plan(prompt, {
        "impact_factor": {"minimum": 10, "user_quote": "影响因子10分以上"},
        "publication_years": {"start": 2026, "end": 2026, "user_quote": "2026年的文章"},
    })
    assert plan == {"publication_years": {"start": 2026, "end": 2026, "user_quote": "2 026年的文章"}}


def test_year_only_eligibility_ignores_old_if_marks():
    trace = SimpleNamespace(record=lambda *args: None)
    records = [{"index": 9, "pubdate": "2026", "_jcr_check": {"passes_threshold": False}},
               {"index": 3, "pubdate": "2026"}]
    years_only = {"publication_years": {"start": 2026, "end": 2026}}
    ledger = assess_eligibility(None, years_only, [], records, trace, {3, 9})
    assert eligibility_lists(ledger, records) == ([9, 3], [])


def test_source_bound_publisher_link_uses_pubmed_locator_after_doi_timeout():
    client = EvidenceFetcher(get=lambda *args, **kw: None)
    correct = "https://www.sciencedirect.com/science/article/pii/S0092867426010810"
    wrong = "https://www.sciencedirect.com/science/article/pii/S0092867426009120"
    source = {"pmid": "42810340", "doi": "10.1016/j.cell.2026.09.012", "link": wrong}
    calls = []
    client.record = lambda _: {"pmid": "42810340", "doi": source["doi"]}

    def read(url, **kwargs):
        calls.append(url)
        if "pubmed.ncbi" in url:
            return f'<a class="link-item dialog-focus" href="{correct}">Publisher</a>'
        if "doi.org" in url:
            raise TimeoutError("temporary")
        assert url == correct
        return f'<meta name="citation_doi" content="{source["doi"]}"><p>Study methods.</p>'

    client.read = read
    article = client.source_article(source)
    assert article["url"] == correct and article["body"] == "Study methods."
    assert wrong not in calls and len(calls) == 3


def test_rate_limit_retry_uses_remaining_evidence_budget(monkeypatch):
    from research_verify import evidence_fetch

    class Response:
        def __init__(self, code, retry_after):
            self.status_code = code
            self.headers = {"Retry-After": str(retry_after)}
            self.closed = False

        def raise_for_status(self):
            if self.status_code == 429:
                raise OSError("rate limited")

        def close(self):
            self.closed = True

        def iter_content(self, _):
            yield b"publication evidence"

    limited = Response(429, 0)
    success = Response(200, 0)
    calls = iter((limited, success))
    monkeypatch.setattr(evidence_fetch, "pace", lambda *args: None)
    client = EvidenceFetcher(get=lambda *args, **kwargs: next(calls), seconds=3, requests=2)
    assert client.read("https://example.org/evidence", service="europepmc") == "publication evidence"
    assert limited.closed and success.closed and client.remaining == 0
    assert [event["status"] for event in client.events] == ["rate_limited", "retrieved"]


def test_confirmed_pmc_page_is_used_when_europepmc_xml_times_out():
    client = EvidenceFetcher(get=lambda *args, **kw: None)
    calls = []

    def read(url, **kwargs):
        calls.append(url)
        if "europepmc" in url:
            raise TimeoutError("request timed out")
        return ('<link rel="canonical" href="https://pmc.ncbi.nlm.nih.gov/articles/PMC456/">'
                '<meta name="citation_doi" content="10.1000/xyz">'
                '<p>Original spatial experiment.</p>')

    client.read = read
    article = client.source_article({"doi": "10.1000/xyz", "pmcid": "PMC456"})
    assert calls[0].endswith("/PMC456/fullTextXML")
    assert calls[1] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC456/"
    assert article["body"] == "Original spatial experiment."


def test_relevance_cap_prioritizes_fresh_results_over_already_screened_rows():
    from threading import Lock
    from local_deep_research.web_search_engines.relevance_filter import filter_previews_for_relevance
    from research_verify.task_plan import search_scope

    calls = []
    model = SimpleNamespace(invoke=lambda prompt: calls.append(prompt) or '{"selected_source_ids": [0]}')
    state = SimpleNamespace(task_question="Study", task_plan={"concepts": [["study"]]},
                            _lock=Lock(), screening_cache={})
    original = {"title": "Known", "doi": "10.1000/old", "abstract": "Previous finding"}
    fresh = {"title": "New", "doi": "10.1000/new", "abstract": "A new qualifying paper"}
    with search_scope(state):
        assert filter_previews_for_relevance(model, [original], "first")[0]["title"] == "Known"
        result = filter_previews_for_relevance(model, [original, fresh], "second", max_filtered_results=1)
    assert result[0]["title"] == "New"
    assert "Previous finding" not in calls[-1]


def test_publisher_html_keeps_headings_tables_and_captions_without_navigation():
    from research_verify.pmc_identity import publisher_article_text

    body = publisher_article_text("""
    <nav>Unrelated links</nav><article><h1>Study title</h1><h2>Methods</h2>
    <p>Tissues were assigned <i>before</i> sampling.</p><figure>
    <figcaption><p>Spatial transcriptomics cohort</p></figcaption></figure>
    <table><tr><th>Groups</th><th>Samples</th></tr><tr><td>Control</td><td>4</td></tr></table>
    </article>""")
    assert "Methods\n\nTissues were assigned before sampling." in body
    assert "Spatial transcriptomics cohort\n\n| Groups | Samples |" in body
    assert "| Control | 4 |" in body and "Unrelated links" not in body


def test_live_milestones_name_direct_source_and_pending_delegation():
    from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy

    format_progress = LangGraphAgentStrategy._format_tool_call_progress
    assert "[56]" in format_progress(None, {"name": "fetch_content", "args": {"source_id": 56}}, "the page")
    assert "pending" in format_progress(None, {"name": "research_subtopic", "args": {}}, "subtopic")
    journal_call = {"name": "search_journal", "args": {"source_index": 56, "journal_name": "Nature Communications"}}
    assert "[56] Nature Communications" in format_progress(None, journal_call, "Journal")



def test_publisher_challenge_page_is_unverified_without_inventing_a_mismatch():
    client = EvidenceFetcher(get=lambda *args, **kw: None)
    client.record = lambda _: None
    client.read = lambda *args, **kwargs: "<p>Checking your browser</p>"
    assert client.source_article({"doi": "10.1000/xyz"}) is None
    assert client.events[-1]["status"] == "identity_unverified"
