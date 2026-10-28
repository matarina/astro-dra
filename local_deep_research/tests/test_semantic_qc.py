"""Model advice no longer requires six dimensions or rule-based overrides."""
from types import SimpleNamespace
import json
import pytest
from research_verify.citation_qc import CitationQc, Claim
from research_verify.semantics import SemanticJudgment


def test_minimal_model_reply_needs_no_fixed_dimensions():
    result=SemanticJudgment.model_validate({"verdict":"supported","supporting_fragment":"A."})
    assert result.verdict=="supported"

@pytest.mark.parametrize('claim,quote', [
    ('X causes disease [1].','X was associated with disease.'),
    ('Treatment improved patients [1].','Treatment improved cultured cells.'),
    ('A 42% reduction [1].','A 12% reduction.'),
])
def test_model_verdict_is_recorded_without_regex_overrides(claim,quote):
    class Judge:
        def invoke(self,prompt):
            assert 'dimensions MUST' not in prompt
            return SimpleNamespace(content=json.dumps({'verdict':'supported','supporting_fragment':quote}))
    source={'doi':'10.1234/test','abstract':quote,'index':1}
    row=CitationQc(Judge()).check([Claim(claim,[1])],SimpleNamespace(find_by_index=lambda n:source))[0]
    # Intentionally wrong model output demonstrates removal of regex vetoes,
    # not the accuracy of this experimental advisory judge.
    assert row.verdict=='supported' and not row.citation_checks[0].semantic_checks
