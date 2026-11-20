import pytest
from research_verify.independent_verification import SourcePassage
from research_verify.source_fact_review import source_fact_prompt,source_fact_questions,parse_source_facts,comparison_notes


def test_reader_questions_are_source_scoped_and_report_is_not_an_input():
    passages=[SourcePassage(8,text='Process A is defined by feature F.',basis='abstract'),
              SourcePassage(9,text='Study B reports observation C.',basis='abstract')]
    questions=source_fact_questions(passages,'Research request')
    assert [q.source_ids for q in questions]==[(8,),(9,)]
    assert len(set(q.question_id for q in questions))==2
    prompt=source_fact_prompt(passages,'Research request')
    assert 'Process A is defined by feature F.' in prompt and 'Study B reports observation C.' in prompt
    with pytest.raises(TypeError):source_fact_prompt(passages,'Request',report='REPORT_ONLY_ANSWER')
    with pytest.raises(ValueError):source_fact_questions([passages[0],passages[0]],'Request')


def test_notes_preserve_missing_answers_and_unlocated_quotes_without_claiming_support():
    passages=[SourcePassage(8,text='Source clause.',basis='abstract'),SourcePassage(9,text='Other text.',basis='abstract')]
    raw='{"answers":[{"question_id":"source-facts-8","status":"supported","answer":"Invented answer","evidence":[{"source_id":8,"quote":"Invented quote"}]}]}'
    answers=parse_source_facts(raw,passages,'Request')
    assert len(answers)==2 and all(a.effective_status=='unknown' for a in answers)
    notes=comparison_notes(answers)
    assert 'Invented answer' in notes and 'not primary evidence' in notes
