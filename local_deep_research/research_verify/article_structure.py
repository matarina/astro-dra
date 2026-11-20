"""Exact own-XML structural locations, including non-experimental material.

All acquired units survive. A structural location is not scientific support;
reference entries do not become the host article's experiments.
"""
import hashlib
import xml.etree.ElementTree as ET

from .article_context import article_context_index
from .retrieval import xml_text
from .source_explanations import unit_registry


def article_structure_index(xml, record, pmid=None):
    identity = article_context_index(xml, record, pmid)
    if identity is None:
        return None
    root = ET.fromstring(xml)
    local = lambda n: n.tag.rsplit('}', 1)[-1]
    if local(root) != 'article':
        return None
    front = next((n for n in root if local(n) == 'front'), None)
    meta = next((n for n in front if local(n) == 'article-meta'), None) if front is not None else None
    if meta is None:
        return None  # A nested article's metadata cannot identify this root.
    parents = {child:parent for parent in root.iter() for child in parent}
    paths = {root:'/article[1]'}
    for parent in root.iter():
        counts = {}
        for child in parent:
            tag = local(child)
            counts[tag] = counts.get(tag, 0) + 1
            paths[child] = paths[parent]+'/'+tag+'['+str(counts[tag])+']'
    entries = []
    # Structural wrappers are not independently selected whole-source units.
    wrappers = {'article','front','body','back','sec','ref-list','article-meta','journal-meta',
                'sub-article','response','floats-group'}
    for node in root.iter():
        if local(node) in wrappers:
            continue
        lineage, cursor = [node], node
        while cursor in parents:
            cursor = parents[cursor]
            lineage.append(cursor)
        lineage.reverse()
        tags = {local(n) for n in lineage}
        if tags & {'sub-article','response'}:
            scope = 'other_article'
        elif tags & {'ref-list','ref','mixed-citation','element-citation'}:
            scope = 'bibliographic_reference'
        elif 'back' in tags:
            scope = 'back_matter'
        elif 'abstract' in tags and meta in lineage:
            scope = 'abstract'
        elif 'body' in tags:
            scope = 'body'
        elif 'floats-group' in tags:
            scope = 'floating_material'
        else:
            scope = 'front_matter'
        sections = []
        for ancestor in lineage:
            if local(ancestor) == 'sec':
                title = next((n for n in ancestor if local(n)=='title'), None)
                sections.append(dict(xml_path=paths[ancestor],section_id=ancestor.get('id'),
                    title=xml_text(title).strip() if title is not None else ''))
        text = xml_text(node).strip()
        if text:
            entries.append(dict(text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                xml_path=paths[node],node_kind=local(node),evidence_scope=scope,section_path=sections,
                containers=[dict(kind=local(n),xml_path=paths[n],original_id=n.get('id'))
                            for n in lineage if local(n) in {'fig','caption','table-wrap','table','ref','supplementary-material'}]))
    return dict(xml_sha256=identity['xml_sha256'],own_article_ids=identity['own_article_ids'],
                entries=entries,semantic_verification='not_performed',visual_content_status='not_inspected_or_transcribed')


def attach_article_structure(units, indexes, *, location_detail='full'):
    """Attach exact locations; ambiguous duplicates retain all possible scopes."""
    unit_registry(units)
    if location_detail not in {'full','scopes'}:
        raise ValueError('Unknown XML location detail')
    output = []
    for unit in units:
        index = indexes.get(unit['source_id'])
        context = dict(status='no_identity_bound_xml',semantic_verification='not_performed')
        if unit.get('kind') != 'text':
            context['status'] = 'metadata_not_xml_text'
        elif index is not None:
            matches = [e for e in index['entries'] if e['text_sha256']==unit['text_sha256'] and e['text']==unit['text']]
            context.update(status='exact_unique_node' if len(matches)==1 else (
                'ambiguous_exact_nodes' if matches else 'no_exact_node'),
                xml_sha256=index['xml_sha256'],own_article_ids=index['own_article_ids'],
                match_count=len(matches),possible_scopes=sorted({e['evidence_scope'] for e in matches}))
            if location_detail == 'full':
                context['locations'] = [{k:v for k,v in e.items() if k not in {'text','text_sha256'}} for e in matches]
            else:
                context['location_detail'] = 'scopes_only_full_locations_in_index'
        output.append({**unit,'original_structure':context})
    return output
