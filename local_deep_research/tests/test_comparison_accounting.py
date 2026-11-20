from research_verify.comparison_accounting import attribute_label_accounting


def test_explicit_model_inconsistency_is_visible_without_rewriting_verdict():
    row=dict(claim_id='a',relation='supported',attribute_findings=[dict(relation='agrees'),dict(relation='differs')])
    r=attribute_label_accounting(row)
    assert r['raw_relation']=='supported'and row['relation']=='supported'
    assert r['scientific_status']=='unassessed_internal_inconsistency'and r['quality_credit']==0


def test_consistent_enums_are_never_scientific_approval():
    row=dict(claim_id='a',relation='supported',attribute_findings=[dict(relation='agrees')])
    r=attribute_label_accounting(row)
    assert r['scientific_status']=='not_semantically_validated'and r['quality_credit']==0
