import hashlib
import json

import pytest

from research_verify.source_explanations import explanation_prompt, parse_explanations, source_explanation_jobs, unit_registry


def unit(material, source, number, text):
    return dict(material_id=material, source_id=source, unit_id=number,
                text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())


def test_explanation_can_bind_several_materials_of_one_article_without_merging_other_sources():
    units = [unit('abstract', 7, 0, 'Study summary.'),
             unit('body', 7, 0, 'First fraction was processed separately.'),
             unit('body', 7, 1, 'The two fractions were pooled.'),
             unit('body', 8, 0, 'Another study.')]
    raw = json.dumps(dict(answers=[dict(source_id=7, explanation='独立处理后合并 [7]。',
        evidence_units=[dict(material_id='body', unit_id=0), dict(material_id='body', unit_id=1)],
        unresolved_scope=''), dict(source_id=8, explanation='', evidence_units=[], unresolved_scope='No relevant methods supplied.')]))
    parsed = parse_explanations(raw, units)
    assert len(parsed[0]['evidence_units']) == 2
    assert parsed[0]['status'] == 'fallible_source_reading_not_semantically_verified'
    assert parsed[1]['explanation'] == '' and parsed[1]['unresolved_scope']


@pytest.mark.parametrize('ref', [dict(material_id='another-paper', unit_id=0),
                                dict(material_id='body', unit_id=True)])
def test_foreign_or_boolean_unit_cannot_supply_a_scientific_explanation(ref):
    units = [unit('body', 7, 0, 'Actual source.'), unit('another-paper', 8, 0, 'Other source.')]
    raw = json.dumps(dict(answers=[dict(source_id=7, explanation='A proposed answer.', evidence_units=[ref], unresolved_scope=''),
                                  dict(source_id=8, explanation='', evidence_units=[], unresolved_scope='Unavailable')]))
    with pytest.raises(ValueError):
        parse_explanations(raw, units)


def test_altered_quote_and_ambiguous_unit_identity_are_rejected():
    u = unit('body', 7, 0, 'Original condition and control.')
    for units in [[u, dict(u)], [{**u, 'text': 'Changed condition.'}]]:
        with pytest.raises(ValueError):
            unit_registry(units)


def test_same_text_in_two_studies_remains_distinct_and_missing_study_is_not_success():
    units = [unit('body', 7, 0, 'Control.'), unit('body', 8, 0, 'Control.')]
    assert len(unit_registry(units)) == 2
    raw = json.dumps(dict(answers=[dict(source_id=7, explanation='', evidence_units=[], unresolved_scope='Unknown')]))
    with pytest.raises(ValueError):
        parse_explanations(raw, units)


def test_source_jobs_preserve_interleaved_materials_context_and_exact_prompt_instruction():
    units = [unit('abstract', 7, 0, 'Summary.'), unit('body', 8, 0, 'Other paper.'),
             {**unit('body', 7, 0, 'Original conditional procedure.'),
              'original_context': {'section_path': ['Original heading']}}]
    before = json.dumps(units)
    jobs = source_explanation_jobs('Original request', units, max_prompt_chars=20000)
    assert [job['source_id'] for job in jobs] == [7, 8]
    assert jobs[0]['units'] == [units[0], units[2]]
    assert jobs[1]['units'] == [units[1]]
    assert json.dumps(units) == before
    assert jobs[0]['prompt'] == explanation_prompt('Original request', [units[0], units[2]])
    delimiter = '\nORIGINAL SOURCE UNITS:\n'
    assert all(job['prompt'].split(delimiter)[0] == explanation_prompt('Original request', units).split(delimiter)[0]
               for job in jobs)


def test_oversized_whole_source_is_not_silently_truncated_or_dropped():
    units = [unit('body', 7, 0, 'Small.'), unit('body', 8, 0, 'x' * 20000)]
    with pytest.raises(ValueError, match='Complete source 8'):
        source_explanation_jobs('Original request', units, max_prompt_chars=10000)


def test_compact_context_is_lossless_source_scoped_and_does_not_mutate_originals():
    from research_verify.source_explanations import compact_context_prompt
    shared=dict(xml_sha256='same document',own_article_ids={'pmid':'123'},semantic_verification='not_performed')
    units=[{**unit('body',sid,0,'Conditional procedure remains complete.'),
            'original_context':{**shared,'status':'exact_unique_paragraph','section_path':['Original section']},
            'original_structure':{**shared,'possible_scopes':['body','bibliographic_reference'],'match_count':2}}
           for sid in [7,8]]
    original=json.dumps(units,sort_keys=True)
    prompt,data=compact_context_prompt('Original request',units)
    assert len(data['documents'])==2
    assert json.dumps(units,sort_keys=True)==original
    assert all(u['text'] in prompt for u in units)
    for old,row in zip(units,data['units']):
        for field in ['original_context','original_structure']:
            context=dict(row[field]);doc=data['documents'][context.pop('xml_context_ref')]
            assert doc['source_id']==row['source_id']
            assert {**doc['shared_context'],**context}==old[field]
