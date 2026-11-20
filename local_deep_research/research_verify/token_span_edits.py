"""Experimental literal-token selection for model-written local replacements.

Token boundaries are generic Unicode lexical boundaries, not scientific rules.
No production caller. Selection, replacement and confirmation remain fallible.
"""
import json
import re
from .field_comparison import edit_prompt,parse_edits
from .request_additions import _json


def anchor_token_registry(report,anchors,source_ids):
    registry=[]
    for a in anchors:
        if not set(a['citation_ids']) & set(source_ids):continue
        text=report[a['start']:a['end']]
        if text!=a['text']:raise ValueError('Original token anchor changed')
        tokens=[dict(token_id=i,start=m.start(),end=m.end(),text=m[0])
                for i,m in enumerate(re.finditer(r'\w+|[^\w\s]',text))]
        registry.append(dict(anchor_id=a['anchor_id'],tokens=tokens))
    return registry


def token_edit_prompt(question,report,material,requirements,anchors,observations,comparisons,source_ids,*,line_local=False):
    registry=anchor_token_registry(report,anchors,source_ids)
    compact=[dict(anchor_id=r['anchor_id'],tokens=[[t['token_id'],t['text']]for t in r['tokens']])for r in registry]
    if line_local:
        texts={a['anchor_id']:a['text']for a in anchors}
        compact=[dict(anchor_id=r['anchor_id'],tokens=[[t['token_id'],t['text'],len(re.findall(r'\r\n|\r|\n',texts[r['anchor_id']][:t['start']]))]for t in r['tokens']])for r in registry]
    prompt=(edit_prompt(question,report,material,requirements,anchors,observations,comparisons)
        +'\nLITERAL TOKEN SELECTION PROTOCOL: For action=replace, omit addition and '
        'replacement_span. Instead emit token_replacements=[{"first_token":0,'
        '"last_token":0,"replacement":"model-written corrected fragment"}]. '
        'Select inclusive token IDs from the chosen anchor in the registry below. '
        'Do NOT retype original text. The program copies the original inclusive '
        'range including interior whitespace, and keeps every other character. '
        'For a field split across a flattened table, use separate nonoverlapping '
        'ranges so other columns stay unchanged. Up to8ranges per anchor; at '
        'most3anchor proposals as before. Never select correct neighboring facts '
        'just to rephrase them. Whole-anchor/deletion-only edits are unrepresented. '
        'For add, use addition as before and omit token_replacements. All existing '
        'source/observation/request IDs and separate confirmation still apply. '
        'Literal selection does not establish scope, support, retention or repair '
        'other occurrences. Do not spend edits duplicating existing information.'
        +'\nACTUAL CITATION-LINKED ANCHOR TOKEN REGISTRY:\n'+json.dumps(compact,ensure_ascii=False))
    if line_local:
        prompt+=('\nLINE-LOCAL EDIT REPRESENTATION: Each registry token is '
            '[token_id,actual_text,original_line_id]. Each replacement range must '
            'stay on ONE original physical line. Correct a field split across '
            'lines with separate nonoverlapping fragments, copying all other '
            'tokens/lines unchanged. Do not select unrelated table columns. '
            'This structural representation does not verify semantic retention '
            'within the chosen range or source support. No whole-row fallback.')
    return prompt


def parse_token_edits(raw,report,material,requirements,anchors,source_ids,observations,*,line_local=False):
    data=_json(raw);rows=data.get('proposals',[])
    if not isinstance(rows,list)or len(rows)>3:raise ValueError('Token proposal bound')
    registry={r['anchor_id']:r for r in anchor_token_registry(report,anchors,source_ids)}
    ar={a['anchor_id']:a for a in anchors};rendered=[];unresolved=[]
    for row in rows:
        p=dict(row)
        if p.get('action')!='replace':
            if 'token_replacements'in p:unresolved.append(dict(proposal=p,reason='token_selection_requires_replace'))
            else:rendered.append(p)
            continue
        aid=p.get('anchor_id');replacements=p.get('token_replacements');bindings=[];selection_issue=None
        valid=(type(aid)is int and aid in registry and isinstance(replacements,list)
            and 1<=len(replacements)<=8 and 'addition'not in p and 'replacement_span'not in p)
        if valid:
            tokens=registry[aid]['tokens'];a=ar[aid];text=a['text']
            for r in replacements:
                first=r.get('first_token');last=r.get('last_token');replacement=r.get('replacement')
                if (type(first)is not int or type(last)is not int or not 0<=first<=last<len(tokens)
                        or not isinstance(replacement,str)or not replacement.strip()):valid=False;break
                start=tokens[first]['start'];end=tokens[last]['end']
                if line_local and ('\n'in text[start:end]or '\r'in text[start:end]):
                    valid=False;selection_issue='token_selection_crosses_original_line';break
                if start==0 and end==len(text):valid=False;break
                bindings.append(dict(start=a['start']+start,end=a['start']+end,
                    original_text=text[start:end],replacement=replacement,first_token=first,last_token=last))
            bindings.sort(key=lambda b:b['start'])
            if any(x['end']>y['start']for x,y in zip(bindings,bindings[1:])):valid=False
        if not valid:
            unresolved.append(dict(proposal=p,reason=selection_issue or 'invalid_or_overlapping_token_selection'));continue
        after=text
        for b in reversed(bindings):
            start=b['start']-a['start'];end=b['end']-a['start'];after=after[:start]+b['replacement']+after[end:]
        p.update(addition=after,literal_anchor_after=after,token_span_bindings=bindings)
        rendered.append(p)
    data['proposals']=rendered
    result=parse_edits(json.dumps(data,ensure_ascii=False),report,material,requirements,anchors,source_ids,observations)
    eligible=[]
    for p in result['eligible']:
        if 'token_span_bindings'in p and p['addition']!=p['literal_anchor_after']:
            unresolved.append(dict(proposal=p,reason='token_render_changed_preserved_bytes'))
        else:eligible.append(p)
    result['eligible']=eligible;result['unresolved'].extend(unresolved)
    return result
