import copy
import json
import pytest

from research_verify.comparison_reconciliation import review_observations,reconciliation_notes


def test_handoff_keeps_disagreement_and_unchecked_without_prior_rewrite_or_mutation():
    claims={0:{'text':'Original [2].'},1:{'text':'A qualifier.'},2:{'text':'Unchecked.'}}
    review={'issues':[{'claim_id':0,'status':'contradiction','replacement':'DO_NOT_COPY',
        'atom_checks':[{'attribute':'relationship','result':'contradiction','replacement':'NESTED_COPY','source_value':'source relation'}]}],
        'checked':[{'claim_id':1,'status':'insufficient_evidence'}]}
    before=copy.deepcopy(review);rows=review_observations(review,claims)
    assert review==before
    assert 'DO_NOT_COPY' not in json.dumps(rows) and 'NESTED_COPY' not in json.dumps(rows)
    assert rows[0]['atom_checks'][0]['source_value']=='source relation'
    assert [r['status'] for r in rows]==['contradiction','insufficient_evidence','unchecked']
    notes=reconciliation_notes(claims,{i:{'text':c['text']} for i,c in claims.items()},{},review,
        {'checked':[{'claim_id':0,'status':'supported'}]})
    assert 'original_language_check' in notes and 'english_reading_check' in notes
    assert 'contradiction' in notes and 'supported' in notes and 'unchecked' in notes
    assert 'DO_NOT_COPY' not in notes


def test_handoff_rejects_unknown_or_duplicate_scope_instead_of_merging_verdicts():
    claims={1:{'text':'Original'}}
    for review in [{'checked':[{'claim_id':2}]},{'checked':[{'claim_id':True}]},
                   {'checked':[{'claim_id':1}],'issues':[{'claim_id':1}]}]:
        with pytest.raises(ValueError):review_observations(review,claims)
