import pytest
from research_verify.claim_language import parse_translations,translation_prompt


def test_translation_contract_rejects_changed_citation_scope_missing_and_duplicate_units():
    claims={4:dict(text='An asserted finding [8].'),5:dict(text='An uncited assertion.')}
    valid='{"translations":[{"claim_id":4,"text":"A translated finding [8]."},{"claim_id":5,"text":"An untranslated premise."}]}'
    assert set(parse_translations(valid,claims))=={4,5}
    with pytest.raises(ValueError,match='source scope'):parse_translations(valid.replace('[8]','[9]'),claims)
    with pytest.raises(ValueError,match='Untranslated'):parse_translations('{"translations":[{"claim_id":4,"text":"Finding [8]."}]}',claims)
    with pytest.raises(ValueError,match='duplicated'):parse_translations(valid.replace('"claim_id":5','"claim_id":4'),claims)


def test_translation_is_source_blind_and_preserves_uncertainty_as_diagnostic_data():
    prompt=translation_prompt({0:dict(text='Literal premise [3].')})
    assert 'Literal premise [3].' in prompt
    with pytest.raises(TypeError):translation_prompt({0:dict(text='Premise')},source='SOURCE_ANSWER')
    result=parse_translations('{"translations":[{"claim_id":0,"text":"Uncertain term [3].","uncertain_terms":["term"]}]}',{0:dict(text='Literal premise [3].')})
    assert result[0]['uncertain_terms']==['term']
def test_fidelity_retains_uncertainty_and_requires_full_scope():
    from research_verify.claim_language import fidelity_prompt, parse_fidelity, bilingual_notes
    import json
    import pytest
    claims={0:{'text':'未定义的 XYZ 可能相关[2]'},1:{'text':'无引用的范围限定'}}
    readings={0:{'text':'Undefined XYZ may be related[2]','uncertain_terms':['XYZ']},1:{'text':'Uncited scope qualifier','uncertain_terms':[]}}
    prompt=fidelity_prompt(claims,readings)
    assert 'No sources are supplied' in prompt and 'XYZ' in prompt
    rows=[{'claim_id':0,'status':'unknown','reason':'Undefined abbreviation'},
          {'claim_id':1,'status':'changed','reason':'Scope may be lost'}]
    parsed=parse_fidelity(json.dumps({'reviews':rows}),claims)
    notes=bilingual_notes(readings,parsed)
    assert 'unknown' in notes and 'changed' in notes and 'Undefined abbreviation' in notes
    for invalid in [rows[:1],rows+[rows[0]],[{**rows[0],'status':'supported'},rows[1]],
                    [{**rows[0],'claim_id':True},rows[1]]]:
        with pytest.raises(ValueError):parse_fidelity(json.dumps({'reviews':invalid}),claims)

