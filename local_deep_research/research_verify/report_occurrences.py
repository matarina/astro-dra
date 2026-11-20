"""Experimental per-occurrence report inventories; no primary-truth verdict."""
import json
from .request_additions import _json
from .request_fields import original_anchors


def parse_occurrence_inventory(raw,texts):
    """Bind each fact separately; invalid facts remain explicit, never repaired."""
    from .retention_inventory import parse_inventory
    rows=_json(raw)['inventories']
    if not isinstance(rows,list):raise ValueError('Invalid occurrence inventories')
    grouped={tid:[]for tid in texts};foreign=[]
    for row in rows:
        if not isinstance(row,dict)or not isinstance(row.get('text_id'),str)or row['text_id']not in grouped:
            foreign.append(dict(raw=row,status='unbound_occurrence'));continue
        grouped[row['text_id']].append(row)
    result=[]
    for tid,matches in grouped.items():
        item=dict(text_id=tid,facts=[],status='not_assessed',rejected_facts=[])
        if len(matches)!=1:
            item['inventory_issue']='missing_or_duplicate_occurrence';item['rejected_rows']=matches
        else:
            facts=matches[0].get('facts')
            if not isinstance(facts,list)or len(facts)>16:
                item['inventory_issue']='invalid_or_oversized_fact_list';item['rejected_rows']=matches
            else:
                counts={}
                for f in facts:
                    if isinstance(f,dict)and type(f.get('fact_id'))is int:counts[f['fact_id']]=counts.get(f['fact_id'],0)+1
                for f in facts:
                    try:
                        if not isinstance(f,dict)or type(f.get('fact_id'))is not int or counts[f['fact_id']]!=1:
                            raise ValueError('Invalid or duplicate occurrence fact ID')
                        bound=parse_inventory(json.dumps(dict(inventories=[dict(text_id=tid,facts=[f])])),{tid:texts[tid]})[0]['facts'][0]
                        item['facts'].append(bound)
                    except (ValueError,TypeError,KeyError):
                        item['rejected_facts'].append(dict(raw=f,status='not_assessed',reason='invalid_fact_or_unlocated_original_lines'))
                item['status']='fallible_text_inventory_with_unassessed_facts'if item['rejected_facts']else'fallible_text_inventory'
        result.append(item)
    return dict(inventories=result,rejected_occurrences=foreign,
        scientific_support_assessed=False,independent_correction_credit=0)


def occurrence_texts(report,source_ids):
    """Every direct citation-linked anchor, with no scientific keyword filter."""
    regions=[a for a in original_anchors(report)if set(a['citation_ids'])&set(source_ids)]
    return {str(a['anchor_id']):a['text']for a in regions}


def comparison_prompt(question,report,inventories):
    return ('Compare statements from DIFFERENT OCCURRENCES within this ONE report. '
        'The inventories are fallible report readings, NOT primary scientific facts. '
        'Rejected facts/rows are unassessed and must not be used as evidence or references. '
        'Recheck exact copied original lines and COMPLETE report context. Group '
        'statements that purport to describe the same study, method, group, field '
        'and quantity unit. Distinguish a compatible total from per-group counts; '
        'people/specimens/sections/cells, new/reused material, abstract availability '
        'and full-text knowledge are different scopes. Do not substitute count '
        'for identifiers or merge different platforms. Identify incompatible '
        'answers AND compatible statements and explain scope differences. Never '
        'declare a report scientifically true, approve an edit, remove content or '
        'infer primary-source support. Every returned fact reference must use '
        'actual text_id/fact_id from supplied inventories. Return JSON only '
        '{"comparisons":[{"fact_refs":[{"text_id":"ID","fact_id":0},'
        '{"text_id":"OTHER_ID","fact_id":0}],"relationship":"conflict|compatible|'
        'different_scope|unknown","reason":"specific actual statements and scope"}]}. '
        'At most128comparisons. Uncompared facts remain unassessed. Do not '
        'invent a comparison for an isolated fact or silently certify all facts.'
        +'\nORIGINAL QUESTION:\n'+question+'\nFALLIBLE PER-OCCURRENCE INVENTORIES:\n'
        +json.dumps(inventories,ensure_ascii=False)+'\nCOMPLETE REPORT:\n'+report)


def parse_comparisons(raw,inventories):
    rows=_json(raw)['comparisons']
    registry={(r['text_id'],f['fact_id']):f for r in inventories for f in r['facts']}
    if not isinstance(rows,list)or len(rows)>128:raise ValueError('Invalid occurrence comparisons')
    compared=set();bound=[]
    for row in rows:
        refs=row.get('fact_refs');reason=row.get('reason')
        if (not isinstance(refs,list)or len(refs)<2 or row.get('relationship')not in {'conflict','compatible','different_scope','unknown'}
                or not isinstance(reason,str)or not reason.strip()):raise ValueError('Invalid occurrence comparison')
        keys=[]
        for r in refs:
            tid=r.get('text_id');fid=r.get('fact_id');key=(tid,fid)
            if not isinstance(tid,str)or type(fid)is not int or key not in registry or key in keys:raise ValueError('Unbound occurrence fact')
            keys.append(key)
        if len({k[0]for k in keys})<2:raise ValueError('Comparison needs distinct occurrences')
        compared.update(keys)
        bound.append(dict(**row,actual_facts=[dict(text_id=t,fact_id=f,**{k:v for k,v in registry[t,f].items()if k!='fact_id'})for t,f in keys],
            assessment_status='fallible_report_consistency_opinion_not_primary_truth'))
    return dict(comparisons=bound,uncompared_facts=[dict(text_id=t,fact_id=f,status='not_assessed')for t,f in registry if (t,f)not in compared],
                unassessed_occurrences=[r['text_id']for r in inventories if r['status']=='not_assessed'],independent_correction_credit=0)
