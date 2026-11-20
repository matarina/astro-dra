"""Experimental exhaustive fact routing with independently read report scope tags.

No scientific truth decisions, production caller or automatic report changes.
"""
import json
from .request_additions import _json
from .occurrence_groups import fact_registry

KINDS={'reported_fact','availability_statement','interpretation','unknown'}
SCOPES={'abstract','full_text','unspecified','not_applicable','unknown'}


def assignment_prompt(question,inventories,descriptors):
    facts={k:dict(text_id=f['text_id'],statement=f['statement'],original_lines=f['original_lines'])for k,f in fact_registry(inventories).items()}
    labels=[{k:g[k]for k in ['group_id','study','method','field','quantity_unit']}for g in descriptors]
    return ('Read EACH actual report fact independently. Assign it to supplied '
        'fallible scope descriptors only if the study/method/field/unit matches. '
        'Descriptors may be wrong; do not force a match. Do not compare truth or '
        'choose only agreeing facts. Include EVERY fact_key exactly once; an '
        'incompatible value can belong to the SAME field descriptor. For no '
        'matching descriptor use[]; missing assignments remainunassessed. '
        'Also read whether the actual statement asserts a reported fact, an '
        'availability statement, an interpretation or unknown; and its stated '
        'availability scope. A count in a report without an explicit access '
        'qualifier has scopeunspecified, not automatically full_text. '
        'Abstract-not-reporting is not paper-not-reporting. Do not infer source '
        'truth. Use compact arrays, NO explanations, NO new facts: {"assignments":'
        '[["actualFactKey",[0],"reported_fact","unspecified"]]}. '
        'Each row=[fact_key,0to3uniquegroup_ids,assertion_kind,availability_scope]. '
        'assertion_kind=reported_fact|availability_statement|interpretation|unknown; '
        'availability_scope=abstract|full_text|unspecified|not_applicable|unknown. '
        'Groups contain no known membership, verdicts or expected answers.'
        +'\nORIGINAL QUESTION:\n'+question+'\nFALLIBLE DESCRIPTORS:\n'+json.dumps(labels,ensure_ascii=False)
        +'\nALL REPORT FACTS WITH ACTUAL LINES:\n'+json.dumps(facts,ensure_ascii=False))


def parse_assignments(raw,inventories,descriptors):
    rows=_json(raw)['assignments'];facts=fact_registry(inventories);gids={g['group_id']for g in descriptors};byid={}
    if not isinstance(rows,list)or len(rows)>len(facts):raise ValueError('Invalid assignment count')
    for row in rows:
        if not isinstance(row,list)or len(row)!=4:raise ValueError('Invalid assignment row')
        key,refs,kind,scope=row
        if (not isinstance(key,str)or key not in facts or key in byid or not isinstance(refs,list)or len(refs)>3
            or any(type(i)is not int or i not in gids for i in refs)or len(set(refs))!=len(refs)
            or not isinstance(kind,str)or kind not in KINDS or not isinstance(scope,str)or scope not in SCOPES):raise ValueError('Unbound assignment')
        byid[key]=dict(fact_key=key,group_ids=refs,assertion_kind=kind,availability_scope=scope,
            actual_fact=facts[key],status='fallible_assignment')
    assignments=[byid.get(k,dict(fact_key=k,group_ids=[],actual_fact=f,status='not_assessed'))for k,f in facts.items()]
    groups=[];unresolved=[]
    for descriptor in descriptors:
        members=[r for r in assignments if descriptor['group_id']in r['group_ids']]
        item={k:descriptor[k]for k in ['group_id','study','method','field','quantity_unit']}
        item['fact_keys']=[m['fact_key']for m in members]
        item['actual_facts']=[dict(fact_key=m['fact_key'],assertion_kind=m['assertion_kind'],availability_scope=m['availability_scope'],**m['actual_fact'])for m in members]
        if len(members)>=2 and len({m['actual_fact']['text_id']for m in members})>=2:groups.append(item)
        else:unresolved.append(dict(**item,status='not_assessed',reason='insufficient_cross_occurrence_members'))
    return dict(assignments=assignments,groups=groups,unresolved_groups=unresolved,
        ungrouped_facts=[r for r in assignments if not r['group_ids']],independent_correction_credit=0)
