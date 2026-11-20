import pytest
from research_verify.proposal_language import proposal_render_prompt,parse_rendered_proposals


def test_source_blind_rendering_keeps_proposed_scope_without_approving_it():
    issues=[dict(claim_id=3,statement='原述[7]。',replacement='A fallible proposed assertion [7].')]
    p=proposal_render_prompt(issues)
    assert '原述' in p and 'A fallible proposed assertion' in p and 'No paper evidence is supplied' in p
    r=parse_rendered_proposals('{"translations":[{"claim_id":3,"text":"候选表述[7]。","uncertain_terms":["name"]}]}',issues)
    assert r[3]['uncertain_terms']==['name']
    with pytest.raises(ValueError):parse_rendered_proposals('{"translations":[{"claim_id":3,"text":"候选表述[8]。"}]}',issues)
    with pytest.raises(ValueError):parse_rendered_proposals('{"translations":[]}',issues)
    with pytest.raises(ValueError):parse_rendered_proposals('{"translations":[]}',issues+issues)
    with pytest.raises(TypeError):proposal_render_prompt(issues,sources='paper')
