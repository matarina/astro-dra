from types import SimpleNamespace

from research_verify import evidence_flow as flow
from research_verify.synthesis_trace import DISABLED


def check(monkeypatch, enabled, reducible):
    # A source formatter may consume its whole allocation while the serialized
    # claim/question/structure adds overhead. The model must see either the
    # entire bounded prompt or no request, never a silently clipped prompt.
    def material(documents, query, claims, required, budget, **kwargs):
        return 'X' * (budget if reducible else 90000), claims
    monkeypatch.setattr(flow, '_review_material', material)
    prompts = []
    def invoke(prompt, **kwargs):
        prompts.append(prompt)
        return '{"issues":[]}'
    reviewer = SimpleNamespace(get_setting=lambda key, default=None:
        enabled if key == 'citation.bound_complete_review_prompt' else default,
        _invoke_text=invoke)
    report = 'A source-attributed finding [9].'
    result = flow.review_answer(reviewer, 'Explain this result.', report,
        [], [{'index':9}], DISABLED, None, 1, 60000, {}, {'remaining':1})
    return prompts, result, report


def test_all_overhead_fits_without_changing_report_or_claim_attribution(monkeypatch):
    prompts, result, report = check(monkeypatch, True, True)
    assert len(prompts) == 1 and len(prompts[0]) <= 60000
    assert report in prompts[0] and 'Explain this result.' in prompts[0]
    assert result[0] == report and result[2] == []


def test_unfittable_source_preserves_report_and_remains_unresolved(monkeypatch):
    prompts, result, report = check(monkeypatch, True, False)
    assert not prompts and result[0] == report and result[2] == []
    assert result[3][0]['reason'] == 'complete_review_prompt_budget'


def test_default_off_preserves_historical_unbounded_behavior(monkeypatch):
    prompts, result, report = check(monkeypatch, False, False)
    assert len(prompts) == 1 and len(prompts[0]) > 60000
    assert result[0] == report


def test_split_keeps_claim_ids_sources_and_complete_material_before_retrieval_loss(monkeypatch):
    import json
    def material(documents, query, claims, required, budget, **kwargs):
        return 'X' * (61000 if len(claims)>1 else 20000), claims
    monkeypatch.setattr(flow, '_review_material', material)
    prompts = []
    def invoke(prompt, **kwargs):
        prompts.append(prompt)
        return '{"issues":[]}'
    reviewer = SimpleNamespace(get_setting=lambda key, default=None:
        True if key == 'citation.bound_complete_review_prompt' else default,
        _invoke_text=invoke)
    report = 'A finding [9].\n\nAnother finding [10].'
    result = flow.review_answer(reviewer,'Question',report,[],
        [{'index':9},{'index':10}],DISABLED,None,1,60000,{}, {'remaining':2})
    assert len(prompts) == 2 and all(len(p)<=60000 for p in prompts)
    claims = [json.loads(p.split('\nFINAL ANSWER:\n')[1].split('\n\nSUPPLIED SOURCES:')[0]) for p in prompts]
    assert [r[0]['claim_id'] for r in claims] == [0,1]
    assert [r[0]['source_ids'] for r in claims] == [[9],[10]]
    assert result[0] == report and result[2] == []
