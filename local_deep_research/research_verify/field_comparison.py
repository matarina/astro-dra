"""Experimental per-field comparison and model-confirmed minimal report edits.

No production caller, rule-written scientific corrections or quality verdicts.
"""
import json

from .request_additions import _json
from .canonical_fields import parse_unit_gaps, MAX_EVIDENCE_UNITS_PER_PROPOSAL


def observations_from_notes(notes,requirements=None):
    observations=[];seen={}
    allowed=None if requirements is None else {r['requirement_id']for r in requirements}
    for batch in notes:
        for source in batch['sources']:
            for field in source['fields']:
                if ('requirement_id'in field)==('requirement_ids'in field):
                    raise ValueError('Ambiguous source-field requirement association')
                refs=field.get('requirement_ids')if 'requirement_ids'in field else[field['requirement_id']]
                if (not isinstance(refs,list)or not refs
                    or any(type(i)is not int or i<0 or allowed is not None and i not in allowed for i in refs)
                    or len(set(refs))!=len(refs)):
                    raise ValueError('Unbound source-field requirement association')
                # Merge only literally identical source observations. In particular,
                # distinct quotes or quantity units are not semantic duplicates.
                fact={k:v for k,v in field.items()if k not in {'requirement_id','requirement_ids'}}
                key=(source['source_id'],json.dumps(fact,sort_keys=True,ensure_ascii=False))
                if key in seen:
                    prior=observations[seen[key]]
                    prior['requirement_ids'].extend(i for i in refs if i not in prior['requirement_ids'])
                else:
                    seen[key]=len(observations)
                    observations.append(dict(observation_id=len(observations),source_id=source['source_id'],
                        requirement_ids=list(refs),**fact))
    return observations


def _context(question,report,material,requirements,anchors,observations):
    return ('\nUSER REQUEST:\n'+question+'\nFALLIBLE REQUEST PLAN:\n'+json.dumps(requirements,ensure_ascii=False)
        +'\nFALLIBLE SOURCE OBSERVATIONS (not gold):\n'+json.dumps(observations,ensure_ascii=False)
        +'\nORIGINAL REPORT ANCHORS:\n'+json.dumps([{k:v for k,v in a.items()if k!='text'}for a in anchors],ensure_ascii=False)
        +'\nCOMPLETE ORIGINAL REPORT:\n'+report+'\nACTUAL SOURCE MATERIAL:\n'+str(material))


def comparison_prompt(question,report,material,requirements,anchors,observations):
    return ('Compare EACH source observation with the COMPLETE original report. '
        'Do not propose edits yet. Preserve original-request scope and verify the '
        'fallible observation against actual source text, including counterevidence. '
        'For each study/modality/group/quantity-unit decide whether the SAME fact '
        'is already present, missing, in conflict, or uncertain. Some platforms '
        'being covered does not cover a different requested platform. A missing '
        'requested field can matter when the rest is correct. Conversely new '
        'wording alone is not new information. Distinguish totals from group '
        'counts, new/reused samples, people/specimens/cells/spots. A conflict '
        'cannot be fixed by merely appending the other value. Locate report '
        'matches/conflicts by original anchor IDs; do not retype anchors. '
        'Unknown eligibility/IF/time/type is not passed. Source observations are '
        'not certified correct merely because their unit exists. Return JSON '
        '{"comparisons":[{"observation_id":0,"state":"present|missing|conflict|uncertain",'
        '"request_quote":"literal original request passage or empty if not requested",'
        '"report_anchor_ids":[0],"reason":"same-scope evidence and comparison"}]}. '
        'Include every observation. Missing records stay unassessed. These are '
        'fallible model comparisons, not independent adjudication.'
        +_context(question,report,material,requirements,anchors,observations))


def parse_comparisons(raw,question,anchors,observations):
    rows=_json(raw)['comparisons'];byid={};ids={o['observation_id']for o in observations};aids={a['anchor_id']for a in anchors}
    if not isinstance(rows,list):raise ValueError('Invalid field comparisons')
    for row in rows:
        oid=row.get('observation_id');refs=row.get('report_anchor_ids',[]);quote=row.get('request_quote','')
        if (type(oid)is not int or oid not in ids or oid in byid or row.get('state')not in {'present','missing','conflict','uncertain'}
            or not isinstance(refs,list)or any(type(i)is not int or i not in aids for i in refs)
            or not isinstance(quote,str)or quote and quote not in question):raise ValueError('Unbound field comparison')
        if row['state']in {'present','conflict'}and not refs:raise ValueError('Unlocated original field')
        byid[oid]=row
    return [byid.get(i,dict(observation_id=i,state='not_assessed',request_quote='',report_anchor_ids=[],reason='Model omitted observation'))for i in sorted(ids)]


def edit_prompt(question,report,material,requirements,anchors,observations,comparisons):
    return ('Propose at most THREE minimal SOURCE-SUPPORTED edits, only where '
        'actual per-field comparison justifies requested missing details or '
        'correction of a source-conflicting report statement. Recheck comparisons; '
        'they are fallible. Use action=add for a novel requested field, replace '
        'for correcting an existing false/conflicting field. Do not merely append '
        'a contradiction or repeat known counts. No deletion-only action, blanket '
        'uncertainty, QC table, extra section, topic filter or unsupported metric. '
        'All text is model-written and separately confirmed; keep correct context, '
        'qualifiers and citations inside a replacement. Outside chosen spans '
        'the entire original stays verbatim. Prefer minimal existing prose spans; '
        'do not break flattened tables. At most one edit per anchor. '
        'Select actual source-unit IDs from the supplied observations; never '
        f'retype quotes. Select 1 to {MAX_EVIDENCE_UNITS_PER_PROPOSAL} unique evidence_units per proposal; '
        'leave a proposal unresolved if its support needs more than this bound. '
        'Unit location does not certify scope/support. Return JSON '
        '{"proposals":[{"action":"add|replace","observation_ids":[0],'
        '"requirement_id":0,"anchor_id":0,"citation_source_ids":[1],'
        '"addition":"complete factual prose to insert or replacement text",'
        '"evidence_units":[{"source_id":1,"unit_id":0}]}]}. '
        'No proposal is acceptable when uncertain; unresolved fields remain visible.'
        +'\nPER-FIELD COMPARISONS:\n'+json.dumps(comparisons,ensure_ascii=False)
        +_context(question,report,material,requirements,anchors,observations))


def parse_edits(raw,report,material,requirements,anchors,source_ids,observations):
    result=parse_unit_gaps(raw,report,material,requirements,anchors,source_ids)
    ids={o['observation_id']for o in observations};eligible=[]
    for proposal in result['eligible']:
        refs=proposal.get('observation_ids')
        if (proposal.get('action')not in {'add','replace'}or not isinstance(refs,list)or not refs
            or any(type(i)is not int or i not in ids for i in refs)):
            result['unresolved'].append(dict(proposal=proposal,reason='invalid_edit_action_or_observation_scope'))
        else:eligible.append(proposal)
    result['eligible']=eligible
    return result


def edit_confirmation_prompt(question,report,material,requirements,anchors,observations,comparisons,proposals):
    return ('Independently check each proposed minimal edit AGAINST actual '
        'source and COMPLETE original report. Do not accept previous labels. '
        'For add: verify the precise requested study/modality/group detail is '
        'new, even when other platforms are covered. For replace: verify original '
        'field actually conflicts with the source and correct original content '
        'inside that span remains. A merely enhanced paraphrase is not needed. '
        'Check every quantity unit, source attribution, qualifier and retained '
        'claim; check other report locations for duplicates or remaining '
        'contradictions. Reject a combined edit that contains unsupported, '
        'redundant or conflicting parts. Do not rewrite the proposal yourself. '
        'All SIX booleans must independently be definite true to apply. Unknown '
        'leaves original unchanged. Explain each failed criterion specifically; '
        'do not set allfalse merely because one criterion fails. Main-platform '
        'coverage alone is not a reason to reject an explicitly requested missing '
        'different modality. Conversely source quote existence is not support. '
        'Return VALID JSON only, closing all arrays/objects: {"decisions":['
        '{"candidate_index":0,"explicitly_requested":false,"source_supported":false,'
        '"same_study_scope":false,"edit_needed":false,"retains_correct_content":false,'
        '"no_new_error":false,"reason":"specific source/report/request comparison"}]}. '
        'This model check is not independent scientific outcome adjudication.'
        +'\nPROPOSED EDITS:\n'+json.dumps(proposals,ensure_ascii=False)
        +'\nFALLIBLE COMPARISONS:\n'+json.dumps(comparisons,ensure_ascii=False)
        +_context(question,report,material,requirements,anchors,observations))


def apply_confirmed_edits(raw,report,proposals):
    decisions=_json(raw)['decisions'];approved=[];seen=set()
    if not isinstance(decisions,list):raise ValueError('Invalid edit confirmation')
    fields=('explicitly_requested','source_supported','same_study_scope','edit_needed','retains_correct_content','no_new_error')
    for decision in decisions:
        i=decision.get('candidate_index')
        if type(i)is not int or not 0<=i<len(proposals)or i in seen:raise ValueError('Unbound edit confirmation')
        seen.add(i)
        if all(decision.get(f)is True for f in fields):approved.append(i)
    changes=[]
    for i in approved:
        p=proposals[i];start=p['anchor_start'];end=p['anchor_end']
        if report[start:end]!=p['anchor']:raise ValueError('Original edit anchor changed')
        if p['action']=='add':start=end;text='\n\n'+p['addition']+'\n'
        elif p['action']=='replace':text=p['addition']
        else:raise ValueError('Invalid confirmed action')
        changes.append(dict(candidate_index=i,start=start,end=end,original_text=report[start:end],replacement=text))
    ordered=sorted(changes,key=lambda c:c['start'])
    if any(a['end']>=b['start']for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping model edits')
    answer=report
    for change in reversed(ordered):answer=answer[:change['start']]+change['replacement']+answer[change['end']:]
    return answer,changes,decisions


def compare_and_edit(question,report,material,requirements,anchors,notes,source_ids,invoke,trace):
    observations=observations_from_notes(notes,requirements)
    comparisons=parse_comparisons(invoke(comparison_prompt(question,report,material,requirements,anchors,observations),
        'per_field_comparison'),question,anchors,observations)
    trace.record('per_field_comparison',dict(observations=observations,comparisons=comparisons))
    edits=parse_edits(invoke(edit_prompt(question,report,material,requirements,anchors,observations,comparisons),
        'field_edit_proposals'),report,material,requirements,anchors,source_ids,observations)
    trace.record('field_edit_proposals',edits)
    answer=report;changes=[];decisions=[]
    if edits['eligible']:
        answer,changes,decisions=apply_confirmed_edits(invoke(edit_confirmation_prompt(question,report,material,requirements,
            anchors,observations,comparisons,edits['eligible']),'field_edit_confirmation'),report,edits['eligible'])
    return answer,dict(observations=observations,comparisons=comparisons,edit_proposals=edits,changes=changes,decisions=decisions)
