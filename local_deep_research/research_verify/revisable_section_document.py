"""Isolated writer experiment: revise fallible notes against original passages.

No production caller. Revisions are model decisions, never automatic scientific
edits. Span binding establishes provenance only, not semantic support.
"""
import copy
import hashlib
import json
import re

from .fact_document import clean_json
from .identity_document import identity_registry
from .section_document import render as render_sections
from .source_span_answers import span_registry


def instructions(sources, registry, views, *, allow_revisions=True):
    passages, _ = span_registry(views)
    return ('Produce one complete useful Chinese report for the original request '
        'using only supplied original sources. The draft is navigation, not '
        'evidence. Reading notes are fallible interpretations. Check their '
        'relationships against original passages: what each quantity counts, '
        'which population, input, assay, comparison or analysis it belongs to, '
        'and the source qualifications. Coexisting analyses need not conflict. '
        'Preserve useful methods, quantities, groups, units and qualifications; '
        'do not replace them with generic uncertainty. Distinguish proposed '
        'experiments from reported experiments. Abstract silence is not a '
        'whole-paper absence. No extra search or outside knowledge. '
        'Return only JSON {"title":"中文报告标题","sections":[{"heading":'
        '"中文章节标题","blocks":[{"kind":"paper","source_id":1,'
        '"fields":["title","journal","publication_year"],"fact_ids":[], '
        '"revisions":[{"fact_id":"1:0","text":"完整修订表述",'
        '"quote_ids":["1:p0"]}],"additional_text":""},{"kind":"analysis",'
        '"purpose":"comparison","text":"中文跨论文分析","source_ids":[]}]}]}. '
        'Select existing fact_ids for each paper. Unrevised selected notes copy '
        'exactly. '+(
        'If a selected note misstates the source, revise its COMPLETE '
        'Chinese text through revisions and cite original passage IDs from that '
        'same paper. Do not preserve an incorrect interpretation just because '
        'it was selected. Revisions apply only to that block occurrence. '
        if allow_revisions else
        'In this arm revisions must be an empty list. Selected notes are copied '
        'verbatim; the writer cannot revise their text. Selection and additional '
        'source-specific prose remain available. ')+ 'Quote '
        'IDs refer to original passages, never to notes or the draft; locating '
        'a passage is not semantic verification. Do not type numeric citation '
        'markers inside fact text. Paper additional_text supplies useful '
        'source-specific information absent from selected notes, without '
        'repeating them. Analysis purpose is comparison, recommendation or '
        'limitation; cite actual source_ids and preserve attribution. Metadata '
        'fields are copied, not retyped. Plan paper blocks inside sections '
        'without repeated paper summaries. No audit table or implementation '
        'labels in the report. All output, including revisions, is fallible.\n'
        'FALLIBLE SOURCE-ANSWER REGISTRY:\n'+json.dumps(registry,ensure_ascii=False)+
        '\nFROZEN IDENTITY FIELD REGISTRY:\n'+json.dumps(identity_registry(sources),ensure_ascii=False)+
        '\nORIGINAL SOURCE PASSAGES:\n'+json.dumps(passages,ensure_ascii=False))


def render(raw, sources, registry, views):
    obj = clean_json(raw)
    normalized = copy.deepcopy(obj)
    expanded = copy.deepcopy(registry)
    byid = {str(v['source_id']): v for v in views}
    _, spans = span_registry(views)
    revisions = []
    for si, section in enumerate(normalized.get('sections', [])):
        for bi, block in enumerate(section.get('blocks', [])):
            if block.get('kind') != 'paper':
                continue
            changes = block.pop('revisions', [])
            if not isinstance(changes, list):
                raise ValueError('Invalid revision list')
            sid = str(block.get('source_id'))
            seen = set()
            for change in changes:
                if not isinstance(change, dict) or set(change) != {'fact_id','text','quote_ids'}:
                    raise ValueError('Invalid revision fields')
                key, text, ids = change['fact_id'], change['text'], change['quote_ids']
                if (not isinstance(key,str) or key not in registry or key in seen
                        or key not in block.get('fact_ids', []) or registry[key]['source_id'] != sid):
                    raise ValueError('Revision must identify one selected same-source note')
                seen.add(key)
                if not isinstance(text,str) or not text.strip() or re.search(r'\[\d+(?:\s*,\s*\d+)*\]',text):
                    raise ValueError('Empty revised note')
                if (not isinstance(ids,list) or not ids or any(not isinstance(q,str) for q in ids)
                        or len(set(ids)) != len(ids)
                        or any(q not in spans or spans[q]['source_id'] != sid for q in ids)):
                    raise ValueError('Revision requires original same-source passages')
                view = byid.get(sid)
                if view is None or hashlib.sha256(view['text'].encode()).hexdigest() != registry[key]['source_view_sha256']:
                    raise ValueError('Revision source view differs from reading-note source')
                # Temporary occurrence IDs let two blocks make distinct decisions
                # without altering the input note or silently revising all uses.
                temporary = '__revision__:'+str(si)+':'+str(bi)+':'+key
                if temporary in expanded:
                    raise ValueError('Revision occurrence ID collision')
                revised = copy.deepcopy(registry[key])
                revised.update(fact_id=temporary,text=text,
                    quotes=[{k:spans[q][k] for k in ('text','start','end')} for q in ids],
                    status='fallible_writer_revision_not_semantic_gold')
                expanded[temporary] = revised
                block['fact_ids'] = [temporary if k == key else k for k in block['fact_ids']]
                revisions.append(dict(temporary_id=temporary,fact_id=key,section_index=si,
                    block_index=bi,source_id=sid,original_note=copy.deepcopy(registry[key]),
                    revised_text=text,quote_ids=ids,original_passages=[copy.deepcopy(spans[q]) for q in ids],
                    source_view_sha256=registry[key]['source_view_sha256'],semantic_support_verified=False))
    report, receipt = render_sections(json.dumps(normalized,ensure_ascii=False), sources, expanded)
    lineage = {r['temporary_id']:r for r in revisions}
    for fact in receipt['facts']:
        key = fact['fact_id']
        if key in lineage:
            fact.update(fact_id=lineage[key]['fact_id'],writer_revised=True,
                original_note_sha256=hashlib.sha256(json.dumps(lineage[key]['original_note'],ensure_ascii=False,sort_keys=True).encode()).hexdigest())
        else:
            fact['writer_revised'] = False
    selected = [lineage[k]['fact_id'] if k in lineage else k for k in receipt['selected_fact_ids']]
    receipt.update(selected_fact_ids=selected,
        unselected_fact_ids=[k for k in registry if k not in selected],
        repeated_fact_ids=list(dict.fromkeys(k for i,k in enumerate(selected) if k in selected[:i])),
        writer_revisions=revisions,automatic_scientific_edits=0)
    return report, receipt
