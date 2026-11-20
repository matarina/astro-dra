"""Own-JATS paragraph context, without inferred experiment labels or verdicts."""
import hashlib
import xml.etree.ElementTree as ET

from .pmc_identity import article_text, _doi
from .retrieval import xml_text
from .source_explanations import unit_registry


def article_context_index(xml, record, pmid=None):
    """Index exact rendered paragraphs with their actual XML ancestry.

    This does not read images, infer headings from prose, or decide support.
    Every explicitly requested own-article identifier must be present and match.
    """
    if article_text(xml, record, pmid, require_body=True) is None:
        return None
    root = ET.fromstring(xml)
    local = lambda node: node.tag.rsplit('}', 1)[-1]
    meta = next(node for node in root.iter() if local(node) == 'article-meta')
    raw_ids = {node.get('pub-id-type'): ''.join(node.itertext()).strip()
               for node in meta if local(node) == 'article-id'}
    own = dict(pmid=raw_ids.get('pmid', ''), pmcid=raw_ids.get('pmc') or raw_ids.get('pmcid', ''),
               doi=raw_ids.get('doi', ''))
    expected = dict(pmid=str(pmid or ''), pmcid=str(record.get('pmcid') or ''),
                    doi=str(record.get('doi') or ''))
    normalize = lambda key, value: (_doi(value) if key == 'doi' else
                                    value.upper().removeprefix('PMC') if key == 'pmcid' else value)
    if not any(expected.values()) or any(value and (not own[key] or
            normalize(key, own[key]) != normalize(key, value)) for key, value in expected.items()):
        return None
    parents = {child: parent for parent in root.iter() for child in parent}
    body = next((node for node in root if local(node) == 'body'), None)
    abstracts = [node for node in meta if local(node) == 'abstract']
    coordinates = {root: '/' + local(root) + '[1]'}
    for parent in root.iter():
        counts = {}
        for child in parent:
            tag = local(child)
            counts[tag] = counts.get(tag, 0) + 1
            coordinates[child] = coordinates[parent] + '/' + tag + '[' + str(counts[tag]) + ']'

    def context(node):
        lineage = []
        while node in parents:
            node = parents[node]
            lineage.append(node)
        lineage.reverse()
        foreign = any(local(n) in {'sub-article', 'response', 'ref-list', 'back'} for n in lineage)
        scope = None if foreign else ('body' if body in lineage else (
            'abstract' if any(n in lineage for n in abstracts) else None))
        sections, containers = [], []
        for ancestor in lineage:
            tag = local(ancestor)
            if tag == 'sec':
                title = next((n for n in ancestor if local(n) == 'title'), None)
                label = next((n for n in ancestor if local(n) == 'label'), None)
                sections.append(dict(xml_path=coordinates[ancestor], section_id=ancestor.get('id'),
                    title=xml_text(title).strip() if title is not None else '',
                    label=xml_text(label).strip() if label is not None else ''))
            if tag in {'fig', 'caption', 'table-wrap', 'table', 'list', 'list-item', 'boxed-text'}:
                containers.append(dict(kind=tag, original_id=ancestor.get('id'), xml_path=coordinates[ancestor]))
        return scope, sections, containers

    paragraphs = []
    for node in root.iter():
        if local(node) != 'p':
            continue
        scope, sections, containers = context(node)
        if scope is None:
            continue  # References, affiliations and unrelated front matter are not body evidence.
        text = xml_text(node).strip()
        if text:
            paragraphs.append(dict(paragraph_ordinal=len(paragraphs), xml_path=coordinates[node],
                evidence_scope=scope, section_path=sections, containers=containers, text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    raw = xml.encode() if isinstance(xml, str) else xml
    return dict(xml_sha256=hashlib.sha256(raw).hexdigest(), own_article_ids=own,
                paragraphs=paragraphs, semantic_verification='not_performed',
                visual_content_status='not_inspected_or_transcribed')


def attach_article_context(units, indexes):
    """Attach only exact unique same-source paragraph context; keep every unit."""
    unit_registry(units)
    output = []
    for unit in units:
        index = indexes.get(unit['source_id'])
        context = dict(status='no_identity_bound_xml', semantic_verification='not_performed')
        if unit.get('kind') != 'text':
            context['status'] = 'metadata_not_a_paragraph'
        elif index is not None:
            matches = [p for p in index['paragraphs'] if p['text'] == unit['text'] and
                       p['text_sha256'] == unit['text_sha256']]
            context.update(status='exact_unique_paragraph' if len(matches) == 1 else (
                'ambiguous_same_text' if matches else 'no_exact_paragraph'),
                xml_sha256=index['xml_sha256'], own_article_ids=index['own_article_ids'],
                match_count=len(matches))
            if len(matches) == 1:
                context.update({key: value for key, value in matches[0].items()
                                if key not in {'text', 'text_sha256'}})
        output.append({**unit, 'original_context': context})
    return output
