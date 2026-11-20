"""Draft-question-informed source answers, not report-blind adjudication."""
from .fact_document import answer_prompt as base_prompt,parse_answers as base_parse
from .fact_document import instructions,render,clean_json


def answer_prompt(question,views):
    return base_prompt(question,views)+(
        '\nADDITIONAL QUESTION COVERAGE INSTRUCTION:\n'
        'Each source record may contain evidence_questions derived from an '
        'UNTRUSTED old report. They identify hypotheses and useful fields to '
        'investigate, NEVER evidence or expected answers. Verify whether their '
        'premises hold; do not copy or agree with them merely because asked. '
        'Read only the actual source text to answer. Some questions route from '
        'another record whose PMID AND DOI exactly agree; this record agreement '
        'does not authenticate the paper or scientific claim. Keep the current '
        'reader source_id and quote only its supplied text. In each fact also '
        'return question_ids:["q0"] for the questions it addresses. Combine '
        'related questions into COMPLETE source-bound paragraphs when needed, '
        'preserving useful sample, assay and group details. Max4facts per source '
        'is unchanged. If the text does not answer a question, retain its '
        'supplied-view limitation; do not infer a whole-study absence. '
        'Question-ID coverage is fallible model accounting, not semantic proof.')


def parse_answers(raw,views):
    parsed=base_parse(raw,views);data=clean_json(raw)
    allowed={str(v['source_id']):{q['question_id']for q in v.get('evidence_questions',[])}for v in views}
    rows={str(row['source_id']):row for row in data['sources']if isinstance(row,dict)and type(row.get('source_id'))in(int,str)}
    missing={sid:set(qids)for sid,qids in allowed.items()};invalid=[]
    for key,fact in parsed['registry'].items():
        sid=fact['source_id'];index=int(key.split(':')[1]);row=rows[sid]['facts'][index]
        ids=row.get('question_ids',[])
        if not isinstance(ids,list)or any(not isinstance(q,str)or q not in allowed[sid]for q in ids)or len(set(ids))!=len(ids):
            invalid.append(dict(fact_id=key,raw_question_ids=ids))
            ids=[]
        fact['model_claimed_question_ids']=ids
        missing[sid].difference_update(ids)
    parsed['model_unaddressed_question_ids']={sid:sorted(ids)for sid,ids in missing.items()if ids}
    parsed['invalid_question_bindings']=invalid
    parsed['semantic_question_coverage_verified']=False
    return parsed
