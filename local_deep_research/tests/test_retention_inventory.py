import json
import hashlib
from dataclasses import replace
import pytest
from research_verify.retention_inventory import (parse_inventory,parse_retention,report_readback_prompt,project_report_regions,
    citation_related_regions,field_question_prompt,parse_field_questions)
from research_verify.independent_verification import SourcePassage,VerificationQuestion


def test_report_readback_cannot_silently_use_article_scope_or_changed_report_bytes():
    text='The report assertion is not primary evidence.'
    p=SourcePassage(source_id=100001,text=text,field='report_text',basis='report_text_only_not_primary_evidence',
        identity={'artifact_sha256':hashlib.sha256(text.encode()).hexdigest()})
    q=VerificationQuestion('q','What does this report state?',source_ids=(100001,))
    prompt=report_readback_prompt([q],[p])
    assert text in prompt and 'DOES NOT mean' in prompt and 'REPORT ARTIFACTS' in prompt
    for changed in [replace(p,field='body'),replace(p,text=text+' changed'),replace(p,basis='primary_fulltext')]:
        with pytest.raises(ValueError):report_readback_prompt([q],[changed])
    with pytest.raises(ValueError):report_readback_prompt([replace(q,source_ids=(5,))],[p])
    nav={'q':[dict(artifact_id=100001,start=0,end=10)]}
    assert text[:10]in report_readback_prompt([q],[p],navigation=nav)
    for invalid in [{'x':nav['q']},{'q':[dict(artifact_id=5,start=0,end=10)]},{'q':[dict(artifact_id=100001,start=0,end=999)]}]:
        with pytest.raises(ValueError):report_readback_prompt([q],[p],navigation=invalid)


def test_report_regions_project_actual_changed_and_untouched_bytes_without_semantic_matching():
    text='First A.\n\nSecond B.\n\nThird C.'
    p=dict(action='replace',anchor_start=0,anchor_end=8,anchor='First A.',addition='New first A.')
    second=text.index('Second');regions={'a':dict(start=0,end=8),'b':dict(start=second,end=second+9)}
    candidate,projected=project_report_regions(text,regions,[p])
    assert candidate[projected['a']['start']:projected['a']['end']]=='New first A.'
    assert candidate[projected['b']['start']:projected['b']['end']]=='Second B.'
    with pytest.raises(ValueError):project_report_regions(text,{'partial':dict(start=1,end=8)},[p])


def test_field_wording_excludes_old_answer_text_and_preserves_scope_fields():
    q=VerificationQuestion('q','OLD ANSWER 9876 expected group',source_ids=(100001,),requested_fields=('patient_identifiers',))
    prompt=field_question_prompt([q]);assert q.text not in prompt and '9876'not in prompt
    parsed=parse_field_questions(json.dumps(dict(questions=[dict(question_id='q',text='Which identifiers, if any, are stated?')])),[q])
    assert parsed[0].source_ids==q.source_ids and parsed[0].requested_fields==q.requested_fields
    with pytest.raises(ValueError):parse_field_questions('{"questions":[]}',[q])


def test_related_citation_regions_preserve_all_linked_occurrences_and_literal_offsets():
    report='One method A [5].\n\nUnrelated B [6].\n\nAnother occurrence C [5].'
    regions=citation_related_regions(report,100001,{5})
    spans=[report[r['start']:r['end']]for r in regions]
    assert any('One method'in t for t in spans)and any('Another occurrence'in t for t in spans)
    assert not any('Unrelated B'in t for t in spans)


def test_inventory_copies_original_linebreaks_and_keeps_missing_text_unassessed():
    texts={'x':'First line\nSecond line\n','y':'Other.'}
    raw=json.dumps(dict(inventories=[dict(text_id='x',facts=[dict(fact_id=0,statement='Fallible reading',line_ids=[0,1])])]))
    parsed=parse_inventory(raw,texts)
    assert ''.join(l['text']for l in parsed[0]['facts'][0]['original_lines'])==texts['x']
    assert parsed[1]['status']=='not_assessed'
    for refs in [[0,0],[True],[99]]:
        with pytest.raises(ValueError):parse_inventory(json.dumps(dict(inventories=[dict(text_id='x',facts=[dict(fact_id=0,statement='x',line_ids=refs)])])),texts)


def test_retention_keeps_missing_fact_rows_and_omitted_source_unknown_distinct():
    pairs=[dict(pair_id='p',original='x',candidate='y')]
    inv=[dict(text_id='x',facts=[dict(fact_id=0),dict(fact_id=1)]),dict(text_id='y',facts=[dict(fact_id=0)])]
    units=[dict(source_id=5,unit_id=2,text='Original source.')]
    row=dict(pair_id='p',original_facts=[dict(fact_id=0,source_support='unknown',retention='omitted',candidate_fact_ids=[],source_unit_ids=[])],candidate_facts=[])
    parsed=parse_retention(json.dumps(dict(pairs=[row])),pairs,inv,units)[0]
    assert parsed['original_facts'][0]['retention']=='omitted'
    assert parsed['original_facts'][1]['status']=='not_assessed'and parsed['candidate_facts'][0]['status']=='not_assessed'
    for change in [dict(fact_id=9),dict(candidate_fact_ids=[9]),dict(source_support='supported'),dict(source_unit_ids=[9])]:
        changed={**row,'original_facts':[{**row['original_facts'][0],**change}]}
        with pytest.raises(ValueError):parse_retention(json.dumps(dict(pairs=[changed])),pairs,inv,units)
    with pytest.raises(ValueError):parse_retention(json.dumps(dict(pairs=[row])),pairs,inv,units+[dict(source_id=9,unit_id=2,text='Other namespace')])
