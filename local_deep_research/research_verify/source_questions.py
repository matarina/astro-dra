"""Fallible draft-derived questions, with provenance but no truth/neutrality claim."""
import json
import re
from .claims import extract_report_claims


def inventory(report):
    rows=[]
    for i,c in enumerate(extract_report_claims(report)):
        if not c.citations:
            continue
        assert report[c.report_start:c.report_end] == c.text
        rows.append(dict(claim_id=str(i),text=c.text,source_ids=c.citations,
                         start=c.report_start,end=c.report_end,context=c.context))
    return rows


def question_prompt(question, claims):
    return ('Create neutral evidence questions to preserve potentially useful '
        'information during NEW report generation. The old report is untrusted '
        'and may be false. It provides questions to investigate, NEVER evidence '
        'or answers. For every registered claim_id create1to3questions, each '
        'bound to ONE of that claim\'s cited source_ids. Ask about the COMPLETE '
        'relationships and scope, not only shared entities. Preserve study/assay '
        'association, sample and group identity, method, quantities and '
        'qualifiers as question dimensions when asserted. Do not include '
        'proposed numeric values, subgroup counts, ages, outcomes, directions '
        'or mechanistic answers from the old report. Do not presuppose that '
        'a study used the reported assay or demonstrated the reported relation; '
        'ask whether and what the source actually establishes. A disputed '
        'proper study name may locate a question, but must not be treated as '
        'authenticated identity. Bibliography-only claims may ask about '
        'identity and relevance without inventing scientific findings. '
        'No report verdict, repair, source evidence or expected answer is '
        'available here. Missing questions remain explicit omissions. '
        'Return JSON {"questions":[{"question_id":"q0","claim_id":"0",'
        '"source_id":1,"question":"中文中性问题，不含原答案"}]}. '
        'Every question max500characters, at most160questions. This is fallible '
        'question generation; matching IDs does not prove neutrality or coverage.\n'
        'ORIGINAL REQUEST:\n'+question+'\nUNTRUSTED CLAIM INVENTORY:\n'+json.dumps(claims,ensure_ascii=False))


def parse_questions(raw, claims):
    obj=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.I))
    if not isinstance(obj,dict) or not isinstance(obj.get('questions'),list):
        raise ValueError('Missing questions')
    known={r['claim_id']:r for r in claims};bound=[];unbound=[];seen=set()
    if len(obj['questions'])>160:
        raise ValueError('Question budget exceeded')
    for row in obj['questions']:
        qid=row.get('question_id') if isinstance(row,dict) else None
        cid=row.get('claim_id') if isinstance(row,dict) else None
        sid=row.get('source_id') if isinstance(row,dict) else None
        text=row.get('question') if isinstance(row,dict) else None
        if (not isinstance(qid,str) or not qid or qid in seen or not isinstance(cid,str) or cid not in known
            or type(sid)is not int or sid not in known[cid]['source_ids']
            or not isinstance(text,str) or not text.strip() or len(text)>500):
            unbound.append(dict(raw=row,reason='Duplicate/foreign reference or invalid field'))
            continue
        seen.add(qid);bound.append(dict(row,status='fallible_question_not_evidence_or_verified_neutral'))
    return dict(questions=bound,unbound_rows=unbound,
                claims_without_questions=[r['claim_id']for r in claims if not any(q['claim_id']==r['claim_id']for q in bound)],
                semantic_coverage_verified=False,answer_leakage_assessed=False)
