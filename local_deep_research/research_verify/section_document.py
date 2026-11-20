"""Experimental paper-block generation, not deduplication of existing reports.

Selected facts and metadata copy exactly; additional paper prose and analyses
remain explicit, fallible generated text. Nothing is semantically approved or
removed, and repeated selections remain in the output with receipts.
"""
import hashlib
import json
from .fact_document import clean_json
from .identity_document import identity_registry, render as render_identity


def instructions(sources, registry):
    return ('\nEXPERIMENTAL COMPLETE-REPORT COMPOSITION:\n'
        'Produce ONE complete useful Chinese report for the original request. '
        'Use the original draft for navigation, never evidence. Sources and '
        'reading notes remain fallible. Plan the sections and put each paper\'s '
        'findings INSIDE its paper block, rather than first writing a prose '
        'summary and then appending the same facts again. Do not repeat a '
        'selected fact in additional_text or an analysis block. Prefer each '
        'paper block and selected fact once unless a substantive comparison '
        'requires otherwise. Do not omit useful requested methods, quantities, '
        'units, groups, qualifiers or appropriate synthesis just to be concise. '
        'Choose relevance and ordering from the original request; collected '
        'papers and old-draft statements are not all eligible or useful. '
        'Return only JSON {"title":"中文报告标题","sections":[{"heading":'
        '"中文章节标题","blocks":[{"kind":"paper","source_id":1,'
        '"fields":["title","journal","publication_year"],'
        '"fact_ids":[],"additional_text":""},{"kind":"analysis",'
        '"purpose":"comparison","text":"中文跨论文分析",'
        '"source_ids":[]}]}]}. No other document/prose layer exists. '
        'A paper block selects existing fact_ids belonging to its source_id; '
        'the program copies their COMPLETE Chinese text and source citation. '
        'Bibliographic fields are selected from the frozen record, not retyped; '
        'metadata agreement and record year are not eligibility certification. '
        'additional_text is available for useful source-specific information '
        'NOT represented by selected reading notes. Write it only from actual '
        'supplied source text, preserve study/assay/sample scope, and do not '
        'invent missing facts. It is NEW fallible prose, not copied or verified '
        'evidence. It may contain normal Markdown, including requested tables. '
        'It receives that paper\'s citation; this does not prove support. '
        'Analysis purpose may be comparison, recommendation or limitation. '
        'Analysis should explain relationships across papers, justified '
        'experimental proposals, or supplied-evidence limits, not duplicate '
        'individual paper summaries. source_ids supply only actual cited '
        'records, not semantic approval. Distinguish a proposed experiment '
        'from a published experiment. Paper additional_text and analysis text '
        'should not type numeric [N] citation markers; the program attaches '
        'their selected source IDs. Headings and analysis remain factual '
        'assessment targets too. No audit table, registry/implementation labels, '
        'extra retrieval or outside knowledge in the report.\n'
        'FALLIBLE SOURCE-ANSWER REGISTRY:\n'+json.dumps(registry,ensure_ascii=False)+
        '\nFROZEN IDENTITY FIELD REGISTRY:\n'+json.dumps(identity_registry(sources),ensure_ascii=False))


def render(raw, sources, registry):
    obj=clean_json(raw)
    if not isinstance(obj,dict)or set(obj)!={'title','sections'}or not isinstance(obj['title'],str)or not isinstance(obj['sections'],list):
        raise ValueError('Invalid complete section document')
    source_ids=set(identity_registry(sources))
    output=[];position=0;facts=[];identities=[];generated=[];headings=[];selected=[];paper_ids=[]
    def emit(value):
        nonlocal position
        start=position;output.append(value);position+=len(value)+2
        return start,start+len(value)
    def prose(text,ids,role,section_index,block_index):
        if not isinstance(text,str):raise ValueError('Invalid generated prose')
        if text:
            value=text+(' ['+','.join(ids)+']'if ids else'')
            start,end=emit(value)
            generated.append(dict(role=role,section_index=section_index,block_index=block_index,
                                  source_ids=ids,text=text,start=start,end=end,
                                  rendered=value,semantic_support_verified=False))
    title='# '+' '.join(obj['title'].splitlines());start,end=emit(title);headings.append(dict(start=start,end=end,text=title))
    for section_index,section in enumerate(obj['sections']):
        if not isinstance(section,dict)or set(section)!={'heading','blocks'}or not isinstance(section['heading'],str)or not isinstance(section['blocks'],list):
            raise ValueError('Invalid section')
        heading='## '+' '.join(section['heading'].splitlines());start,end=emit(heading);headings.append(dict(start=start,end=end,text=heading))
        for block_index,block in enumerate(section['blocks']):
            if not isinstance(block,dict):raise ValueError('Invalid composition block')
            if block.get('kind')=='paper':
                if set(block)!={'kind','source_id','fields','fact_ids','additional_text'}:
                    raise ValueError('Invalid paper block fields')
                sid=block['source_id']
                if type(sid)not in(int,str)or str(sid)not in source_ids:raise ValueError('Unknown paper source')
                sid=str(sid);paper_ids.append(sid)
                if not isinstance(block['fact_ids'],list):raise ValueError('Invalid fact selection')
                identity,receipts=render_identity(json.dumps({'nodes':[dict(kind='identity',source_id=sid,heading_level=3,fields=block['fields'])]},ensure_ascii=False),sources)
                start,_=emit(identity)
                identities.extend(dict(r,start=r['start']+start,end=r['end']+start,section_index=section_index,block_index=block_index)for r in receipts)
                for key in block['fact_ids']:
                    if not isinstance(key,str)or key not in registry or registry[key]['source_id']!=sid:
                        raise ValueError('Unknown or foreign paper fact selection')
                    fact=registry[key];value=fact['text']+' ['+sid+']';start,end=emit(value);selected.append(key)
                    facts.append(dict(fact_id=key,source_id=sid,start=start,end=end,rendered=value,section_index=section_index,block_index=block_index,
                                      fact_sha256=hashlib.sha256(json.dumps(fact,ensure_ascii=False,sort_keys=True).encode()).hexdigest()))
                prose(block['additional_text'],[sid],'additional_paper_text',section_index,block_index)
            elif block.get('kind')=='analysis':
                if set(block)!={'kind','purpose','text','source_ids'}or block['purpose']not in('comparison','recommendation','limitation'):
                    raise ValueError('Invalid analysis block')
                ids=block['source_ids']
                if not isinstance(ids,list)or any(type(s)not in(int,str)or str(s)not in source_ids for s in ids):
                    raise ValueError('Unknown analysis citation')
                # Citation identity normalization only; preserve all prose and
                # repeated fact/paper selections, never deduplicate science.
                ids=list(dict.fromkeys(str(s)for s in ids))
                prose(block['text'],ids,block['purpose'],section_index,block_index)
            else:raise ValueError('Unknown composition block kind')
    return '\n\n'.join(output),dict(facts=facts,identities=identities,generated_prose=generated,headings=headings,
        selected_fact_ids=selected,unselected_fact_ids=[k for k in registry if k not in selected],
        repeated_fact_ids=list(dict.fromkeys(k for i,k in enumerate(selected)if k in selected[:i])),
        repeated_paper_ids=list(dict.fromkeys(k for i,k in enumerate(paper_ids)if k in paper_ids[:i])),
        semantic_verdict=None,automatic_prose_deletions=0)
