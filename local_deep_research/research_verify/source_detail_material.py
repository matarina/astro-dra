"""Candidate-only source-original detail packing with serialized budget receipts."""
import hashlib
import json
from .generation import SourceMaterial
from .source_reader_candidate import source_segments


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def format_source_details(documents, request, receipts, *, max_chars, required_ids=(),
                          max_source_chars=8000):
    docs={int(d.metadata['index']):d for d in documents}
    cache={int(r['source_id']):r for r in receipts}
    if len(cache)!=len(receipts) or set(cache)!=set(docs):
        raise ValueError('Reader/source namespace mismatch')
    candidates={};unread={}
    for sid,d in docs.items():
        r=cache[sid];text=str(d.page_content or '')
        if r['source_sha256']!=_sha(text) or r['request_sha256']!=_sha(request):
            raise ValueError('Reader source/request hash mismatch')
        # Derive emitted intervals from canonical segment indices, not cached
        # model-written text or merged cache extents.
        segments=source_segments(text)
        if 'selected_segment_indices' in r:
            indices=r['selected_segment_indices']
            if (not isinstance(indices,list) or len(indices)!=len(set(indices)) or
                    any(type(i) is not int or not 0<=i<len(segments) for i in indices)):
                raise ValueError('Invalid reader segment index')
            candidates[sid]=[(segments[i].start,segments[i].end) for i in sorted(indices)]
        else:
            intervals=[]
            for span in r['spans']:
                a,b=span['start'],span['end']
                if (type(a) is not int or type(b) is not int or not 0<=a<b<=len(text)
                        or span['text']!=text[a:b] or span['text_sha256']!=_sha(text[a:b])):
                    raise ValueError('Invalid canonical reader span')
                intervals.append((a,b))
            candidates[sid]=list(dict.fromkeys(intervals))
        unread[sid]=list(r['unread_segment_indices'])
    required={int(i) for i in required_ids}
    if not required<=set(docs):
        raise ValueError('Unknown required source')
    notice=('SOURCE-ORIGINAL REQUEST DETAILS. These are model-selected candidate intervals, '
            'not semantic verification. Gaps, omitted material and unread windows remain unknown. '
            'Metadata is supplied identity data, not proof of eligibility.\n\n')
    def merged(intervals):
        out=[]
        for a,b in sorted(intervals):
            if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(b,out[-1][1]))
            else:out.append((a,b))
        return out
    def block(sid,intervals):
        d=docs[sid];meta={k:v for k,v in d.metadata.items()
                         if k not in {'abstract','index','title','source'} and v not in (None,'',[],{})}
        header=f'[{sid}]\nTitle: {d.metadata.get("title","")}\nURL: {d.metadata.get("source","")}\n'
        header+='Supplied metadata (unverified): '+json.dumps(meta,ensure_ascii=False,sort_keys=True)+'\n'
        if not intervals:
            return header+'No selected original-text interval supplied; this does not establish absence in the study.'
        return header+'\n\n'.join(f'Canonical source offsets {a}:{b}; source SHA-256 {_sha(d.page_content)}\n'
                                  +d.page_content[a:b] for a,b in merged(intervals))
    selected={sid:[] for sid in required}
    order=sorted(docs,key=lambda sid:(_sha(docs[sid].page_content),str(docs[sid].metadata.get('source',''))))
    def render(items):
        return notice+'\n\n'.join(block(sid,items[sid]) for sid in order if sid in items)
    if len(render(selected))>max_chars:
        raise ValueError('Required source identity headers exceed detail budget')
    allocation=[]
    chosen=set()
    def attempt(sid,ordinal,limit,lane):
        a,b=candidates[sid][ordinal]
        proposal={key:list(value) for key,value in selected.items()}
        proposal.setdefault(sid,[]).append((a,b))
        source_fits=len(block(sid,proposal[sid]))<=max_source_chars
        total_fits=len(render(proposal))<=limit
        accepted=source_fits and total_fits
        if accepted:
            selected.clear();selected.update(proposal);chosen.add((sid,ordinal))
        allocation.append(dict(source_id=sid,start=a,end=b,lane=lane,
                               state='selected' if accepted else
                               'omitted_source_budget' if not source_fits else
                               'deferred_lane_budget' if lane=='source_seed' else 'omitted_total_budget'))
    # Reserve continuation capacity instead of consuming the whole budget on
    # one introductory quote per source. Shares match the predeclared structural
    # design; source round order is content-based, never feedback-based.
    seed_budget=max(len(render(selected)),int(max_chars*0.6))
    for sid in order:
        if candidates[sid]:attempt(sid,0,seed_budget,'source_seed')
    for ordinal in range(max((len(v) for v in candidates.values()),default=0)):
        for sid in order:
            if sid in selected and ordinal<len(candidates[sid]) and (sid,ordinal) not in chosen:
                attempt(sid,ordinal,max_chars,'continuation')
    # Unused continuation capacity may be borrowed by previously unserved sources.
    for sid in order:
        if sid not in selected and candidates[sid]:attempt(sid,0,max_chars,'borrowed_seed')
    material=render(selected);views={}
    for sid,intervals in selected.items():
        text='\n\n[... source excerpt boundary ...]\n\n'.join(docs[sid].page_content[a:b] for a,b in merged(intervals))
        views[sid]=dict(index=sid,text=text,block=block(sid,intervals),
                        available_chars=len(docs[sid].page_content),model_view_chars=len(text),
                        available_sha256=_sha(docs[sid].page_content),model_view_sha256=_sha(text),
                        scope='selected canonical source intervals; other text not supplied',view_kind='source_detail_indices',
                        exhaustive_assessment=False,canonical_intervals=merged(intervals))
    final_allocation=[dict(source_id=sid,start=a,end=b,state='selected' if (sid,i) in chosen else 'omitted_budget')
                      for sid in order for i,(a,b) in enumerate(candidates[sid])]
    receipt=dict(schema_version='source_detail_material.v1',request_sha256=_sha(request),
                 max_chars=max_chars,max_source_chars=max_source_chars,seed_budget_chars=seed_budget,material_chars=len(material),
                 material_sha256=_sha(material),registry_ids=sorted(views),allocation=allocation,final_allocation=final_allocation,
                 unread_segments={str(k):v for k,v in unread.items() if v},
                 note='Source-coordinate integrity and budget allocation only; no support or correction claim')
    return SourceMaterial(material,views),receipt
