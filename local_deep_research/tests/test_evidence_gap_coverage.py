"""Offline checks for the opt-in source-scoped evidence-gap candidate arm."""

import importlib.util
from pathlib import Path


def _runner():
    path = Path(__file__).parents[2] / "scripts/run_hallucination_next_phase_experiment_20261113.py"
    spec = importlib.util.spec_from_file_location("next_phase_runner_gap", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gap_receipt_bounds_complete_text_and_preserves_hashes():
    runner = _runner()
    body = (
        "Methods used flow cytometry and a named sequencing platform.\n\n"
        "The population included eight samples.\n\n"
    ) * 800
    receipt = runner._gap_receipt(
        {
            "query": "single-cell assay and platform",
            "questions": ["population", "assay and platform"],
        },
        [{"index": "1", "title": "Synthetic source", "body": body,
          "content_type": "full_text"}],
    )
    context = receipt["writer_context"]
    assert sum(len(item["text"]) for item in context) <= 150000
    assert receipt["complete_source_context"]["selected_chars"] <= 150000
    for item in context:
        assert item["text_sha256"]
        assert item["source_text_sha256"]
        assert item["method"] in {"complete_acquired_text", "coverage_planner", "lexical_hint_with_structural_anchors"}
    assert receipt["coverage_plan"]["note"].startswith("candidate availability")


def test_gap_receipt_reserves_a_cited_source_for_candidate_coverage():
    runner = _runner()
    receipt = runner._gap_receipt(
        {
            "query": "study method",
            "questions": ["method"],
        },
        [{"index": "1", "title": "Cited source", "body": "Unrelated supplied text.",
          "content_type": "full_text"}],
        context_budget=4000,
        draft="A cited statement [1].",
    )
    assert 1 in receipt["coverage_plan"]["priority_source_ids"]
    assert "1" in receipt["coverage_plan"]["source_ids"]


def test_candidate_attachment_receipt_binds_attached_and_omitted_cards():
    from types import SimpleNamespace
    from research_verify.generation import format_source_documents

    doc = SimpleNamespace(page_content="Original method text.", metadata={
        "index": 7, "title": "Source 7", "source": "https://example.org/7",
    })
    receipts = []
    output = format_source_documents(
        [doc], max_chars=2000,
        candidate_passages=[{
            "source_id": 7, "field": "method", "text": "Original method text.",
            "start": 0, "end": 21, "text_sha256": __import__("hashlib").sha256(
                b"Original method text.").hexdigest(),
            "source_text_sha256": __import__("hashlib").sha256(
                b"Original method text.").hexdigest(),
            "method": "coverage_planner", "relevance_hint": 0.7,
        }, {
            "source_id": 99, "field": "missing", "text": "never supplied",
            "start": 0, "end": 14,
            "text_sha256": __import__("hashlib").sha256(b"never supplied").hexdigest(),
            "source_text_sha256": "source-hash-99", "method": "candidate",
        }],
        candidate_attachment_receipts=receipts,
    )
    assert output and len(receipts) == 1
    receipt = receipts[0]
    assert receipt["attached_count"] == 1
    assert receipt["omitted_count"] == 1
    attached = next(card for card in receipt["cards"] if card["source_id"] == 7)
    omitted = next(card for card in receipt["cards"] if card["source_id"] == 99)
    assert attached["status"] == "attached"
    assert attached["offsets"] == {"start": 0, "end": 21}
    assert omitted["status"] == "omitted"
    assert omitted["omission_reason"] == "invalid_card_binding"
    assert receipt["final_source_material_sha256"] == __import__("hashlib").sha256(
        str(output).encode()).hexdigest()


def test_candidate_attachment_receipt_rejects_tampered_hashes_and_offsets():
    from types import SimpleNamespace
    from research_verify.generation import format_source_documents

    text = "duplicate passage; duplicate passage"
    receipts = []
    format_source_documents([SimpleNamespace(page_content=text, metadata={
        "index": 3, "title": "S", "source": "u"})], max_chars=2000,
        candidate_passages=[
            {"source_id": 3, "field": "x", "text": "duplicate passage", "start": 1, "end": 18,
             "text_sha256": "tampered", "source_text_sha256": "tampered"},
            {"source_id": 3, "field": "x", "text": "duplicate passage", "start": 0, "end": 17,
             "text_sha256": __import__("hashlib").sha256(b"duplicate passage").hexdigest(),
             "source_text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest()},
            {"source_id": 3, "field": "x", "text": "duplicate passage", "start": 19, "end": 36,
             "text_sha256": __import__("hashlib").sha256(b"duplicate passage").hexdigest(),
             "source_text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest()},
        ], candidate_attachment_receipts=receipts)
    cards = receipts[0]["cards"]
    assert cards[0]["status"] == "omitted"
    assert cards[0]["omission_reason"] == "invalid_card_binding"
    assert cards[1]["status"] == "attached"
    assert cards[2]["status"] == "attached"


def _formatted_receipt_fixture():
    import hashlib
    from types import SimpleNamespace
    from research_verify.generation import format_source_documents

    value = "prefix duplicate prose; duplicate prose suffix"
    passage = "duplicate prose"
    start = value.index(passage)
    item = dict(source_id=804, field='attribute', text=passage,
                start=start, end=start + len(passage),
                text_sha256=hashlib.sha256(passage.encode()).hexdigest(),
                source_text_sha256=hashlib.sha256(value.encode()).hexdigest())
    receipts = []
    material = format_source_documents(
        [SimpleNamespace(page_content=value, metadata={
            'index': 804, 'title': 'Synthetic', 'source': 'https://example.invalid/synthetic'})],
        max_chars=10000, reading_scope=[], candidate_passages=[item],
        candidate_attachment_receipts=receipts)
    return material, receipts, item


def test_candidate_attachment_receipt_refreshes_after_final_append():
    import hashlib
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    final_text = str(material) + "\nAdditional unrelated text."
    refresh_candidate_attachment_receipts(receipts, final_text, list(material.views), [item])
    assert receipts[0]['cards'][0]['status'] == 'attached'
    assert receipts[0]['post_append_refreshed'] is True
    assert receipts[0]['final_context_chars'] == len(final_text)
    assert receipts[0]['final_source_material_sha256'] == hashlib.sha256(final_text.encode()).hexdigest()


def test_refresh_distinguishes_bound_block_without_registry_source():
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    refresh_candidate_attachment_receipts(receipts, str(material), [], [item])
    card = receipts[0]['cards'][0]
    assert card['status'] == 'attached_text_registry_absent'
    assert card['omission_reason'] is None
    assert receipts[0]['attached_count'] == 1


def test_attachment_receipts_survive_result_json_serialization():
    import json
    receipts = [{
        "schema_version": "candidate_attachment_receipt.v1",
        "cards": [{"source_id": 7, "status": "attached",
                   "offsets": {"start": 0, "end": 4},
                   "text_sha256": "t", "source_text_sha256": "s"}],
        "final_source_material_sha256": "m", "final_context_chars": 4,
        "final_registry_ids": [7], "fallback_path": "none",
    }]
    encoded = json.dumps({"candidate_attachment_receipts": receipts}, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["candidate_attachment_receipts"][0]["cards"][0]["offsets"] == {
        "start": 0, "end": 4}
    assert decoded["candidate_attachment_receipts"][0]["final_registry_ids"] == [7]


def test_refresh_does_not_attach_unbound_fallback_prose():
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    # Bare prose and a matching registry ID do not preserve the canonical block.
    refresh_candidate_attachment_receipts(receipts, item['text'], [804], [item])
    assert receipts[0]['cards'][0]['status'] == 'omitted'
    assert receipts[0]['cards'][0]['omission_reason'] == 'unverified_source_block_binding'


def test_refresh_rejects_changed_offsets_despite_duplicate_text():
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    later = {**item, 'start': item['start'] + len('duplicate prose; '),
             'end': item['end'] + len('duplicate prose; ')}
    # Text hash is unchanged; full card identity must not resolve to the earlier card.
    refresh_candidate_attachment_receipts(receipts, material, list(material.views), [later])
    assert receipts[0]['cards'][0]['status'] == 'omitted'


def test_refresh_rejects_mismatched_final_registry_source_hash():
    from copy import deepcopy
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    registry = deepcopy(material.views)
    registry[804]['available_sha256'] = '0' * 64
    refresh_candidate_attachment_receipts(receipts, str(material), registry, [item])
    assert receipts[0]['cards'][0]['status'] == 'omitted'


def test_refresh_rejects_tampered_card_offsets_and_material_block():
    from copy import deepcopy
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    changed = deepcopy(receipts)
    changed[0]['cards'][0]['offsets']['start'] += 1
    refresh_candidate_attachment_receipts(changed, material, list(material.views), [item])
    assert changed[0]['cards'][0]['status'] == 'omitted'
    final_text = str(material).replace('Title: Synthetic', 'Title: Different', 1)
    refresh_candidate_attachment_receipts(receipts, final_text, list(material.views), [item])
    assert receipts[0]['cards'][0]['status'] == 'omitted'


def test_refresh_receipts_remain_valid_after_json_roundtrip():
    import json
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    restored = json.loads(json.dumps(receipts))
    refresh_candidate_attachment_receipts(restored, str(material), list(material.views), [item])
    assert restored[0]['cards'][0]['status'] == 'attached'
    assert restored[0]['cards'][0]['delivery_binding']['source_text_sha256'] == item['source_text_sha256']


def test_receipt_collection_does_not_change_formatter_output_or_registry():
    from types import SimpleNamespace
    from research_verify.generation import format_source_documents

    material, receipts, item = _formatted_receipt_fixture()
    source = 'prefix duplicate prose; duplicate prose suffix'
    doc = SimpleNamespace(page_content=source, metadata={
        'index': 804, 'title': 'Synthetic', 'source': 'https://example.invalid/synthetic'})
    without_receipts = format_source_documents(
        [doc], max_chars=10000, reading_scope=[], candidate_passages=[item])
    assert str(material) == str(without_receipts)
    assert material.views == without_receipts.views


def test_refresh_rejects_changed_source_id_or_source_hash_with_same_prose():
    from copy import deepcopy
    from research_verify.generation import refresh_candidate_attachment_receipts

    material, receipts, item = _formatted_receipt_fixture()
    for replacement in ({'source_id': 805}, {'source_text_sha256': '0' * 64}):
        copied = deepcopy(receipts)
        refresh_candidate_attachment_receipts(
            copied, str(material), [804, 805], [{**item, **replacement}])
        assert copied[0]['cards'][0]['status'] == 'omitted'
