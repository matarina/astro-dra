"""Acquired-source discovery for uncited prose; never assign its citations."""
import hashlib
from .generation import SourceMaterial
from .passages import retrieve_passages
from .material_exposure import capture_writer_exposure


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def discovery_material(documents, query, existing, max_chars):
    """Retain existing blocks and every remaining complete supplied abstract.

    Whole acquired-text windows may use remaining space. If the complete
    abstract inventory cannot fit, expose unavailability rather than a silently
    selected source subset. Discovery relevance is not claim attribution.
    """
    original = str(existing)
    views = dict(getattr(existing, 'views', {}) or {})
    docs = list(documents)
    ids = [int(d.metadata['index']) for d in docs]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate source IDs in discovery pool')
    if original and capture_writer_exposure(existing) is None:
        raise ValueError('Existing source blocks require bound views')
    extra = [d for d in docs if int(d.metadata['index']) not in views]
    texts, headers, windows = {}, {}, {}
    for d in extra:
        m = d.metadata
        sid = int(m['index'])
        abstract = m.get('abstract')
        texts[sid] = abstract if isinstance(abstract, str) else ''
        one = lambda value: ' '.join(str(value or '').splitlines())
        headers[sid] = f"[{sid}]\nTitle: {one(m.get('title'))}\nURL: {one(m.get('source'))}\n"
        for label, key in [('DOI', 'doi'), ('PMID', 'pmid'), ('Date', 'publication_date')]:
            if m.get(key):
                headers[sid] += f'{label}: {one(m[key])}\n'
        headers[sid] += ('Evidence type: source-discovery candidate; complete supplied abstract when present; '
                         'additional acquired excerpts if marked; other metadata not shown; '
                         'published-paper completeness unconfirmed\n')
        windows[sid] = []

    def blocks():
        return [headers[int(d.metadata['index'])] + 'BEGIN SOURCE TEXT\n'
                + texts[int(d.metadata['index'])] + '\nEND SOURCE TEXT' for d in extra]

    def serialized():
        return '\n\n'.join(([original] if original else []) + blocks())

    receipt = dict(pool_source_ids=ids, existing_source_ids=sorted(views),
                   discovery_source_ids=[int(d.metadata['index']) for d in extra],
                   original_material_sha256=digest(original), max_material_chars=max_chars,
                   claim_source_ids_modified=False, attribution='unassigned_search_candidates',
                   semantic_support='not_assessed', windows=[])
    if len(serialized()) > max_chars:
        return existing, receipt | dict(status='unavailable_complete_abstract_inventory_budget',
                                        minimum_chars=len(serialized()), attached_source_ids=[])
    # Round-robin windows across the entire pool; no scientific/topic rules or
    # claim-source association is inferred from retrieval scores.
    candidates = {}
    for d in extra:
        sid = int(d.metadata['index'])
        candidates[sid] = [p for p in retrieve_passages(d.page_content or '', query,
            window_chars=900, max_passages=2, overlap_chars=150) if p.text not in texts[sid]]
    omitted = []
    for rank in range(2):
        for d in extra:
            sid = int(d.metadata['index'])
            if rank >= len(candidates[sid]):
                continue
            p = candidates[sid][rank]
            assert (d.page_content or '')[p.start:p.end] == p.text
            previous = texts[sid]
            addition = f'\n\nADDITIONAL ACQUIRED EXCERPT (characters {p.start}:{p.end}):\n' + p.text
            texts[sid] += addition
            row = dict(source_id=sid, start=p.start, end=p.end, text_sha256=digest(p.text))
            if len(serialized()) > max_chars:
                texts[sid] = previous
                omitted.append(row)
            else:
                windows[sid].append(row)
                receipt['windows'].append(row)
    rendered_blocks = blocks()
    for d, block in zip(extra, rendered_blocks):
        sid = int(d.metadata['index'])
        text = texts[sid]
        views[sid] = dict(index=sid, text=text, block=block, model_view_chars=len(text),
            model_view_sha256=digest(text), available_chars=len(d.page_content or ''),
            available_sha256=digest(d.page_content or ''), view_kind='unassigned_discovery_abstract_and_excerpts',
            scope='Complete supplied abstract when present; bounded acquired excerpts; unassigned to claims',
            exhaustive_assessment=False)
    result = SourceMaterial(serialized(), views)
    capture_writer_exposure(result)
    assert len(result) <= max_chars
    return result, receipt | dict(status='attached_unassigned_candidates',
        attached_source_ids=[int(d.metadata['index']) for d in extra],
        empty_discovery_source_ids=[int(d.metadata['index']) for d in extra if not texts[int(d.metadata['index'])]],
        omitted_windows=omitted, material_chars=len(result), material_sha256=digest(str(result)),
        original_material_preserved=True)
