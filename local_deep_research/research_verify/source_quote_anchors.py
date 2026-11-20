"""Canonical source intervals from model quote hints; never validate hint claims.

A model-normalized value is not copied into evidence. Only source-original bytes
between two unique, exact anchors are returned, with a non-verbatim-hint state.
"""
from hashlib import sha256


def locate_quote_hint(hint, source, *, view_start=0, view_end=None, anchor_chars=40,
                      max_extent_chars=2000):
    view_end = len(source) if view_end is None else view_end
    if (type(view_start) is not int or type(view_end) is not int or
            not 0 <= view_start <= view_end <= len(source) or
            type(anchor_chars) is not int or anchor_chars < 20):
        raise ValueError('invalid canonical view or anchor limits')
    if not isinstance(hint,str) or not hint:
        return None
    view=source[view_start:view_end]
    if view.count(hint)==1:
        a=view.index(hint)
        b=a+len(hint)
        method='exact_quote'
    else:
        if len(hint)<2*anchor_chars:
            return None
        first,last=hint[:anchor_chars],hint[-anchor_chars:]
        if view.count(first)==1 and view.count(last)==1:
            a=view.index(first)
            b=view.index(last)+len(last)
            if b-a<2*anchor_chars:
                return None
            method='unique_boundary_anchors_nonverbatim_hint'
        else:
            # Retrieval fallback only: two or more unique, non-overlapping
            # interior anchors must preserve ordering and approximately their
            # separation. Emit surrounding ORIGINAL bytes, never hint wording.
            anchors=[]
            for offset in range(0,len(hint)-anchor_chars+1,anchor_chars):
                token=hint[offset:offset+anchor_chars]
                if view.count(token)==1:
                    anchors.append((offset,view.index(token)))
            if len(anchors)<2:
                return None
            if any(y[1]<=x[1] or abs((y[1]-x[1])-(y[0]-x[0]))>200
                   for x,y in zip(anchors,anchors[1:])):
                return None
            first_hint,first_source=anchors[0]
            last_hint,last_source=anchors[-1]
            a=max(0,first_source-first_hint-80)
            b=min(len(view),last_source+len(hint)-last_hint+80)
            method='unique_interior_anchors_source_context_retrieval'

    if not 0 < b-a <= max_extent_chars:
        return None
    a+=view_start;b+=view_start
    text=source[a:b]
    return dict(start=a,end=b,text=text,text_sha256=sha256(text.encode()).hexdigest(),
                source_sha256=sha256(source.encode()).hexdigest(),method=method,
                hint_sha256=sha256(hint.encode()).hexdigest(),hint_verbatim=hint==text,
                note='Original-source interval only; model hint wording is not verified or emitted as evidence')
