"""Isolated question-to-record aliases from TWO agreeing stable identifiers.

Records and questions stay unchanged. Agreement is routing evidence only, not
independent authentication, scientific entailment or a title-based paper merge.
"""
import re


def key(source):
    pmid=str(source.get('pmid') or '').strip()
    doi=str(source.get('doi') or '').strip().lower()
    if not re.fullmatch(r'[1-9][0-9]*',pmid) or not re.fullmatch(r'10\.\d{4,9}/\S+',doi):
        return None
    return pmid,doi


def route_questions(questions,sources):
    byid={str(s['index']):s for s in sources}
    if len(byid)!=len(sources):raise ValueError('Duplicate source IDs')
    keys={sid:key(s)for sid,s in byid.items()}
    pmids={};dois={};pmcs={}
    for sid,pair in keys.items():
        if pair:
            pmids.setdefault(pair[0],set()).add(pair[1])
            dois.setdefault(pair[1],set()).add(pair[0])
            pmc=str(byid[sid].get('pmcid')or'').strip().upper()
            if pmc:pmcs.setdefault(pair,set()).add(pmc)
    result=[]
    for q in questions:
        original=str(q['source_id'])
        if original not in byid:raise ValueError('Question source not registered')
        pair=keys[original]
        candidates=[original]
        reason='original_source_only_no_unambiguous_two_identifier_alias'
        if pair and len(pmids[pair[0]])==1 and len(dois[pair[1]])==1 and len(pmcs.get(pair,set()))<=1:
            candidates=[]
            own_pmc=str(byid[original].get('pmcid')or'').strip().upper()
            for sid,other in byid.items():
                other_pmc=str(other.get('pmcid')or'').strip().upper()
                if keys[sid]==pair and not(own_pmc and other_pmc and own_pmc!=other_pmc):
                    candidates.append(sid)
            reason='exact_pmid_and_doi_record_agreement_no_observed_identifier_conflict'
        for target in candidates:
            result.append(dict(question_id=q['question_id'],claim_id=q['claim_id'],
                               original_source_id=original,reader_source_id=target,
                               question=q['question'],route_reason=reason,
                               shared_identifiers=None if not pair else dict(pmid=pair[0],doi=pair[1]),
                               independently_authenticated=False,semantic_verdict=None))
    return result
