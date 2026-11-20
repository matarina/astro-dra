from research_verify.rendering_diagnostics import patch_rendering_diagnostics


def test_detects_new_unclosed_tail_without_rewriting_or_verdict():
    p=dict(anchor='Count（value\nmethod and identifiers\nend）[5]',addition='Count（new value）\nmethod and identifiers\nend）[5]')
    before=dict(p);r=patch_rendering_diagnostics([p]);assert p==before
    chinese=next(x for x in r[0]['counts']if x['opening']=='（')
    assert chinese['before_balance']==0 and chinese['after_balance']==-1 and chinese['absolute_imbalance_increased']
    assert not next(x for x in r[0]['counts']if x['opening']=='[')['absolute_imbalance_increased']
    assert not {'approved','source_supported','corrected'}&r[0].keys()


def test_does_not_treat_preexisting_imbalance_as_new_or_claim_balanced_text_is_correct():
    r=patch_rendering_diagnostics([dict(anchor='Unclosed (',addition='Still unclosed (')])[0]
    assert not any(x['absolute_imbalance_increased']for x in r['counts'])
