"""Experimental minimal literal report revisions; no production caller or scientific rules."""
import json
from .request_additions import _json
from .report_syntax import citations_in


def _context(question,report,material,anchors,units,index_preview_chars=100):
    if index_preview_chars not in (24,100):raise ValueError('Index preview bound')
    index=[dict(source_id=u['source_id'],unit_id=u['unit_id'],kind=u['kind'],preview=u['text'][:index_preview_chars])for u in units]
    anchor_index=[{k:(v[:index_preview_chars]if k=='preview'else v)for k,v in a.items()if k!='text'}for a in anchors]
    return ('\nORIGINAL USER REQUEST:\n'+question+'\nREPORT ANCHOR INDEX:\n'
        +json.dumps(anchor_index,ensure_ascii=False)
        +'\nCOMPLETE REPORT:\n'+report+'\nSOURCE UNIT INDEX (not extra evidence):\n'
        +json.dumps(index,ensure_ascii=False)+'\nACTUAL REGISTERED SOURCE MATERIAL:\n'+str(material))


def revision_prompt(question,report,material,anchors,units,*,index_preview_chars=100):
    return ('Propose at most8minimal literal-span corrections to this COMPLETE '
        'report using actual supplied original sources. No prior support verdict, '
        'feedback, expected repair or gold answer is provided. Only correct a '
        'specific source-conflicting identity/relation/scope/fact; do not merely '
        'enhance prose, delete requested useful content, translate the report, '
        'add a QC table, impose eligibility gates or invent missing metadata. '
        'Metadata establishes bibliographic attributes, not complete paper '
        'methods or historical writer exposure. Unreported in an abstract is '
        'not false in a full article. An unknown record/IF is unresolved. '
        'Inspect headings/tables/bibliography and all repeated report locations; '
        'a correct value elsewhere does not settle a conflicting location. '
        'Choose the SMALLEST continuous original quote within a registered '
        'anchor; model-copy it literally, including PDF line breaks/spaces. '
        'Replacement must preserve original language, correct surrounding '
        'qualifiers, citation IDs and table layout. No deletion-only edit. '
        'Select original source unit IDs, never rewrite evidence quotations. '
        'Return JSON {"proposals":[{"anchor_id":int,"original":str,'
        '"replacement":str,"evidence_units":[{"source_id":int,"unit_id":int}],'
        '"reason":str}],"unresolved":str}. Each original/replacement max1000'
        'characters, reason max400. Uncertain suggestions remain unresolved. '
        'This is candidate drafting, not independent scientific adjudication.'
        +_context(question,report,material,anchors,units,index_preview_chars))


def _citation_ids(text):return {i for c in citations_in(text)for i in c.indices}


def parse_proposals(raw,report,anchors,units):
    data=_json(raw);rows=data.get('proposals',[])
    if not isinstance(rows,list)or len(rows)>8:raise ValueError('Finite revision proposal bound')
    byanchor={a['anchor_id']:a for a in anchors};byunit={(u['source_id'],u['unit_id']):u for u in units};valid=[];unresolved=[]
    for n,row in enumerate(rows):
        try:
            aid=row.get('anchor_id');original=row.get('original');replacement=row.get('replacement');refs=row.get('evidence_units',[])
            if type(aid)is not int or aid not in byanchor:raise ValueError('Unregistered report anchor')
            a=byanchor[aid]
            if report[a['start']:a['end']]!=a['text']:raise ValueError('Stale original anchor')
            if not isinstance(original,str)or not original or len(original)>1000 or not isinstance(replacement,str)or not replacement.strip()or len(replacement)>1000 or replacement==original:raise ValueError('Original/replacement bound')
            if a['text'].count(original)!=1:raise ValueError('Unlocated or ambiguous original fragment')
            if _citation_ids(original)!=_citation_ids(replacement):raise ValueError('Changed citation IDs inside fragment')
            if not isinstance(refs,list)or not refs or len(refs)>4:raise ValueError('Evidence reference bound')
            evidence=[]
            for ref in refs:
                sid=ref.get('source_id');uid=ref.get('unit_id')
                if type(sid)is not int or type(uid)is not int or(sid,uid)not in byunit:raise ValueError('Unregistered source unit')
                evidence.append(byunit[(sid,uid)])
            start=a['start']+a['text'].index(original);reason=row.get('reason','')
            if not isinstance(reason,str)or len(reason)>400:raise ValueError('Reason bound')
            valid.append(dict(candidate_index=len(valid),proposal_index=n,start=start,end=start+len(original),original_text=original,replacement=replacement,evidence_units=evidence,reason=reason,anchor_id=aid,association_status='model_source_association_unadjudicated'))
        except(ValueError,KeyError,TypeError)as exc:unresolved.append(dict(proposal_index=n,raw=row,reason=str(exc)))
    ordered=sorted(valid,key=lambda c:c['start'])
    if any(a['end']>b['start']for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping literal revisions')
    return dict(proposals=valid,unlocated_proposals=unresolved,model_unresolved=data.get('unresolved',''))


def apply_proposals(report,proposals):
    answer=report
    ordered=sorted(proposals,key=lambda c:c['start'])
    if any(a['end']>b['start']for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping literal revisions')
    for p in reversed(ordered):
        if report[p['start']:p['end']]!=p['original_text']:raise ValueError('Stale original revision')
        answer=answer[:p['start']]+p['replacement']+answer[p['end']:]
    return answer


def confirmation_prompt(question,candidate,material,anchors,units,proposals,*,index_preview_chars=100):
    shown=[{k:v for k,v in p.items()if k!='evidence_units'}|dict(evidence_refs=[dict(source_id=u['source_id'],unit_id=u['unit_id'])for u in p['evidence_units']])for p in proposals]
    return ('Evaluate each proposed literal revision against original sources '
        'and the COMPLETE resulting report. Do not trust prior reasons. Old '
        'fragments and exact original positions appear below; all text outside '
        'them is mechanically unchanged. Check scientific identity, population,'
        'scope, attribution, every number/qualifier, language and layout; '
        'inspect other occurrences for remaining conflicts/new inconsistencies. '
        'Do not call a wrong mechanism or subgroup a harmless simplification. '
        'Do not delete supported detail because abstracts omit it. Source unit '
        'existence is not entailment. Unknown must be null, never approval. '
        'Return JSON {"decisions":[{"candidate_index":int,"original_conflicts":'
        'true|false|null,"replacement_supported":true|false|null,"same_source_scope":'
        'true|false|null,"useful_content_retained":true|false|null,"no_new_error":'
        'true|false|null,"language_layout_retained":true|false|null,"reason":str}]}. '
        'All six criteria need separate reasons in reason; no scientific gold '
        'or correction credit supplied. Entire batch stays unapplied if any '
        'proposal is missing/uncertain/rejected. No repair of proposal text here.'
        +'\nPROPOSED LITERAL CHANGES:\n'+json.dumps(shown,ensure_ascii=False)
        +_context(question,candidate,material,[],units,index_preview_chars))


def confirmation_decisions(raw,proposals):
    rows=_json(raw).get('decisions',[]);ids={p['candidate_index']for p in proposals};seen=set()
    if not isinstance(rows,list):raise ValueError('Invalid revision confirmations')
    fields=('original_conflicts','replacement_supported','same_source_scope','useful_content_retained','no_new_error','language_layout_retained')
    for row in rows:
        i=row.get('candidate_index')
        if type(i)is not int or i not in ids or i in seen:raise ValueError('Unbound revision decision')
        if any(row.get(f)is not None and type(row[f])is not bool for f in fields):raise ValueError('Invalid revision decision value')
        seen.add(i)
    approved=bool(proposals)and seen==ids and all(row.get(f)is True for row in rows for f in fields)
    return dict(batch_approved=approved,decisions=rows,missing_candidate_indices=sorted(ids-seen),status='model_confirmation_not_independent_assessment')


def revision_anchors(report):
    from .evidence_flow import review_units
    anchors=[]
    for unit in review_units(report):
        start,end=unit.report_start,unit.report_end
        if report[start:end]!=unit.text:raise ValueError('Nonliteral revision unit')
        anchors.append(dict(anchor_id=len(anchors),start=start,end=end,text=unit.text,
            preview=unit.text[:100],citation_ids=unit.citations,kind=unit.kind))
    return anchors
