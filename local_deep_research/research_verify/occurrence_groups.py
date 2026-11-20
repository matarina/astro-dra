"""Experimental grouping before bounded report consistency reading; no truth gate."""
import json
from .request_additions import _json


def fact_registry(inventories):
    facts={}
    for row in inventories:
        for f in row['facts']:
            key='f'+str(len(facts))
            facts[key]=dict(text_id=row['text_id'],**f)
    return facts


def grouping_prompt(question,inventories):
    compact={k:{field:f[field]for field in ['text_id','statement']}for k,f in fact_registry(inventories).items()}
    return ('Organize fallible REPORT statements for later comparison. Do not judge '
        'truth or compare all pairs. Group repeated descriptions of the SAME '
        'study/method/field/quantity-unit across DIFFERENT text_id occurrences. '
        'Keep different papers, methods, identifiers vs counts, people vs '
        'specimens, totals vs per-group counts separate. Availability qualifiers '
        '(abstract vs fulltext) are distinct scopes; do not silently erase them. '
        'Do not group arbitrary facts merely sharing a citation. Use at most24 '
        'groups,2to16actual fact_keys per group, at least2different text_id values. '
        'A fact may participate in different relevant groups. Do not invent '
        'facts/values, discard difficult claims, or call ungrouped facts correct. '
        'No reason/verdict/pairwise enumeration. Return JSON only {"groups":['
        '{"group_id":0,"study":"reported study identity","method":"reported method",'
        '"field":"one field","quantity_unit":"actual unit or not_applicable",'
        '"fact_keys":["f0","f1"]}]}. Each descriptor max120characters. '
        'Grouping is a fallible interpretation; ungrouped facts stay unassessed.'
        +'\nORIGINAL QUESTION:\n'+question+'\nREPORT FACTS:\n'+json.dumps(compact,ensure_ascii=False))


def parse_groups(raw,inventories):
    rows=_json(raw)['groups'];registry=fact_registry(inventories);seen=set();groups=[];unresolved=[];used=set()
    if not isinstance(rows,list)or len(rows)>24:raise ValueError('Invalid occurrence group bound')
    for row in rows:
        gid=row.get('group_id');refs=row.get('fact_keys');reason=None
        if type(gid)is not int or gid<0 or gid in seen:reason='invalid_or_duplicate_group_id'
        elif any(not isinstance(row.get(k),str)or not row[k].strip()or len(row[k])>120 for k in ['study','method','field','quantity_unit']):reason='missing_scope_descriptor'
        elif not isinstance(refs,list)or not 2<=len(refs)<=16 or any(not isinstance(k,str)or k not in registry for k in refs)or len(set(refs))!=len(refs):reason='unbound_group_facts'
        elif len({registry[k]['text_id']for k in refs})<2:reason='group_needs_distinct_occurrences'
        if type(gid)is int:seen.add(gid)
        if reason:unresolved.append(dict(raw=row,status='not_assessed',reason=reason));continue
        used.update(refs);groups.append(dict(**row,actual_facts=[dict(fact_key=k,**registry[k])for k in refs],assessment_status='fallible_grouping'))
    return dict(groups=groups,unresolved_groups=unresolved,ungrouped_facts=[dict(fact_key=k,**f,status='not_assessed')for k,f in registry.items()if k not in used],independent_correction_credit=0)


def group_comparison_prompt(question,report,grouped):
    return ('Read each supplied group against its actual copied REPORT lines and '
        'complete report. Group labels and inventories are fallible: verify '
        'same study/method/field/quantity unit before judging. Return ONE result '
        'per group, not pairwise combinations. Conflict requires incompatible '
        'answers to the SAME scope. Abstract availability is not whole-paper '
        'absence. Different scopes can be compatible; an unknown relation stays '
        'unknown. Locate relevant corroborating/counter statements by the supplied '
        'fact_keys. No primary source is supplied: never approve edits or infer '
        'scientific support. Return JSON {"results":[{"group_id":0,'
        '"relationship":"conflict|compatible|different_scope|unknown",'
        '"relevant_fact_keys":["actualKey","otherActualKey"],'
        '"reason":"scope-specific explanation, max350characters"}]}. '
        'At most24results; omitted groups stay unassessed. Rejected/ungrouped '
        'facts remain unassessed; do not claim whole-report completeness.'
        +'\nORIGINAL QUESTION:\n'+question+'\nFALLIBLE GROUPS WITH ACTUAL LINES:\n'
        +json.dumps(grouped['groups'],ensure_ascii=False)+'\nCOMPLETE REPORT:\n'+report)


def parse_group_comparisons(raw,grouped):
    rows=_json(raw)['results'];registry={g['group_id']:g for g in grouped['groups']};parsed={}
    if not isinstance(rows,list)or len(rows)>24:raise ValueError('Invalid group result bound')
    for row in rows:
        gid=row.get('group_id');refs=row.get('relevant_fact_keys');reason=row.get('reason')
        if type(gid)is not int or gid not in registry or gid in parsed:raise ValueError('Unbound group result')
        facts={f['fact_key']:f for f in registry[gid]['actual_facts']}
        if (row.get('relationship')not in {'conflict','compatible','different_scope','unknown'}or not isinstance(refs,list)
            or len(refs)<2 or any(not isinstance(k,str)or k not in facts for k in refs)or len(set(refs))!=len(refs)
            or len({facts[k]['text_id']for k in refs})<2 or not isinstance(reason,str)or not reason.strip()or len(reason)>350):raise ValueError('Unbound group comparison')
        parsed[gid]=dict(**row,actual_facts=[facts[k]for k in refs],assessment_status='fallible_report_consistency_not_primary_truth')
    return [parsed.get(gid,dict(group_id=gid,status='not_assessed'))for gid in registry]
