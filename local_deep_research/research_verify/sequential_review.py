"""Experimental English second pass on an already native-reviewed report.

No writer, publication or production caller. Optional bounded acquisition follows
an explicit model evidence request. Every
original-language edit still goes through the existing semantic confirmation.
"""
import hashlib
import json
import re

from .claim_language import translation_prompt,parse_translations
from .proposal_language import proposal_render_prompt,parse_rendered_proposals
from .source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS
from .evidence_flow import (review_claim_groups,document_structure_spans,required_sources,
    _review_material,review_prompt,literal_assertion_spans,parse_review,confirm_repairs,supplement,apply_review)


PRESENTATION_NOTE=('These units are a diagnostic presentation of report assertions. Their presentation '
    'language does not change the original report language or establish article language/eligibility. '
    'Assess factual meaning against the supplied sources; no report is being rewritten.')


def english_review_prompt(base, translations):
    prefix,tail=base.split('\nFINAL ANSWER:\n',1)
    payload,suffix=tail.split('\n\nSUPPLIED SOURCES:',1)
    original=json.loads(payload)
    if {x['claim_id'] for x in original}!=set(translations):raise ValueError('Translation scope differs from native prompt')
    english=[{**c,'text':translations[c['claim_id']]['text'],
        'literal_assertion_spans':literal_assertion_spans(translations[c['claim_id']]['text'])} for c in original]
    return (prefix+'\nFINAL ANSWER:\n'+json.dumps(english,ensure_ascii=False)+'\n\nSUPPLIED SOURCES:'+suffix
        +'\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS+'\n\n'+PRESENTATION_NOTE)


def sequential_english_review(handler,question,answer,documents,sources,trace,call_budget,context_budget=60000,network_state=None):
    start=answer;groups=review_claim_groups(start,documents,sources,question,context_budget)
    structure=document_structure_spans(start);reserve=min(8000,len(json.dumps(structure,ensure_ascii=False)))
    context=question+'\nExisting report headings (destinations must use these exact headings):\n'+'\n'.join(re.findall(r'^#{1,6} .+',start,re.M))
    applied_all=[];pending_all=[];receipts=[]
    def digest(text):return hashlib.sha256(text.encode()).hexdigest()
    def invoke(prompt,**kw):
        if len(prompt)>context_budget:raise ValueError('Sequential review prompt exceeds declared budget')
        if call_budget['remaining']<=0:raise TimeoutError('Sequential review call budget exhausted')
        call_budget['remaining']-=1;return handler._invoke_text(prompt,trace=trace,**kw)
    trace.record('sequential_start',dict(report_sha256=digest(start),groups=len(groups),units=sum(len(g) for g in groups)))
    for number,claims in enumerate(groups,1):
        if call_budget['remaining']<=0:
            pending_all.append(dict(status='sequential_budget_exhausted',unreviewed_groups=len(groups)-number+1));break
        receipt=dict(group=number,claim_ids=list(claims),status='prepared',applied=0)
        group_pending=[]
        try:
            readings=None;group_pending=[]
            for round_no in range(2):
                section='\n'.join(c['text'] for c in claims.values())
                material,prompt_claims=_review_material(documents,question+'\n'+section,claims,required_sources(section,sources),max(2000,context_budget-reserve))
                base=review_prompt(context,section,material,claims=prompt_claims,structure_spans=structure,prompt_budget=context_budget,identity_attributes=True)
                trace.record('sequential_group_input',dict(group=number,round=round_no+1,claims=claims,base_prompt=base,material=str(material),
                    material_views=getattr(material,'views',{}),material_sha256=digest(str(material)),report_sha256=digest(start)))
                if readings is None:
                    readings=parse_translations(invoke(translation_prompt(claims),stage='sequential_translation'),claims)
                else:
                    # Evidence changes, original report text and its source-blind
                    # presentation do not. Never translate a prior proposed answer.
                    readings={k:readings[k] for k in claims}
                english_prompt=english_review_prompt(base,readings)
                english_claims={k:{**v,'text':readings[k]['text']} for k,v in claims.items()}
                raw=invoke(english_prompt,stage='sequential_english_check')
                issues,checked=parse_review(raw,english_claims,include_checked=True)
                trace.record('sequential_group_review',dict(group=number,round=round_no+1,readings=readings,issues=issues,checked=checked))
                mapped=[{**i,'presentation_statement':i.get('statement'),'statement':claims[i['claim_id']]['text']}
                        for i in issues if i.get('claim_id') in claims]
                group_pending=[i for i in issues if i.get('claim_id') not in claims]
                proposals=[i for i in mapped if i.get('status') in {'contradiction','scope_correction','version_update'} and i.get('replacement')]
                group_pending.extend(i for i in mapped if i not in proposals)
                receipt.update(status='checked',issues=len(issues),checked=len(checked),proposals=len(proposals),rounds=round_no+1,
                    material_sha256=digest(str(material)),english_prompt_sha256=digest(english_prompt))
                if proposals:
                    rendered=parse_rendered_proposals(invoke(proposal_render_prompt(proposals),stage='sequential_proposal_rendering'),proposals)
                    originals=[{**i,'replacement':rendered[i['claim_id']]['text']} for i in proposals]
                    trace.record('sequential_group_proposals',dict(group=number,round=round_no+1,issues=originals,renderings=rendered))
                    get_setting=getattr(handler,'get_setting',lambda k,d=None:d)
                    if get_setting('citation.literal_quote_reselection',False):
                        targets=[]
                        for index,issue in enumerate(originals):
                            _,eligible,rejected=apply_review(answer,[issue],material)
                            if not eligible and any(i.get('unlocated_quote_count',0)>0 for i in rejected):
                                targets.append(index)
                        if targets:
                            from .quote_reselection import quotation_prompt,parse_quote_updates
                            try:
                                selected=[originals[i]for i in targets]
                                updated,quote_receipts=parse_quote_updates(invoke(quotation_prompt(selected,material),
                                    stage='sequential_quote_reselection'),selected,material)
                                originals=list(originals)
                                for index,issue in zip(targets,updated,strict=True):originals[index]=issue
                                trace.record('sequential_quote_reselection',dict(group=number,round=round_no+1,
                                    target_indices=targets,issues=originals,receipts=quote_receipts))
                            except Exception as exc:
                                trace.record('sequential_quote_reselection_invalid',dict(group=number,
                                    round=round_no+1,error_type=type(exc).__name__))
                    answer,applied,pending=confirm_repairs(handler,answer,originals,material,question,trace,
                        invoke=lambda p,**kw:invoke(p,stage=kw.get('stage','repair_validation')))
                    applied_all.extend(applied);group_pending.extend(pending);receipt['applied']+=len(applied)
                if round_no or network_state is None or not any(i.get('request') for i in group_pending):break
                from .evidence_fetch import EvidenceFetcher
                fetcher=network_state.get('fetcher')
                if fetcher is None:
                    fetcher=EvidenceFetcher(getattr(handler,'settings_snapshot',{}),seconds=45,requests=16)
                    network_state['fetcher']=fetcher
                new_ids=supplement(group_pending,sources,fetcher,register=None,trace=trace)
                if not new_ids:break
                trace.record('sequential_followup_sources',dict(group=number,source_ids=new_ids))
                documents=handler._create_documents(sources)
                targets={i.get('statement') for i in group_pending if i.get('request')}
                followup_claims={k:v for k,v in claims.items() if v['text'] in targets and v['text'] in answer}
                # Keep pending states for claims outside the explicit followup.
                if not followup_claims:break
                pending_all.extend(i for i in group_pending if i.get('statement') not in targets)
                claims=followup_claims
                # Retain the previous request until the refreshed check succeeds.
            pending_all.extend(group_pending)
        except Exception as exc:
            receipt.update(status='unavailable',error_type=type(exc).__name__)
            pending_all.extend(group_pending)
            pending_all.append(dict(status='sequential_group_unavailable',group=number,error_type=type(exc).__name__))
        receipts.append(receipt);trace.record('sequential_group_receipt',receipt)
    trace.record('sequential_complete',dict(report_sha256=digest(answer),applied=len(applied_all),remaining_calls=call_budget['remaining'],receipts=receipts))
    return answer,applied_all,pending_all,receipts
