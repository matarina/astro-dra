"""Internal model-label consistency accounting, never a scientific verdict or gate."""


def attribute_label_accounting(comparison):
    raw=comparison.get('relation');findings=comparison.get('attribute_findings',[])
    flags=[]
    if raw=='supported'and any(f.get('relation')=='differs'for f in findings):
        flags.append('supported_label_with_explicit_attribute_difference')
    if raw=='contradicted'and findings and all(f.get('relation')=='agrees'for f in findings):
        flags.append('contradicted_label_with_only_declared_agreement')
    return dict(claim_id=comparison['claim_id'],raw_relation=raw,internal_flags=flags,
        scientific_status='unassessed_internal_inconsistency'if flags else'not_semantically_validated',
        quality_credit=0)
