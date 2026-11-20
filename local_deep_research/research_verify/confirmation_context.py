"""Optional complete acquired source context for native repair confirmation.

This changes evidence exposure, not repair eligibility or semantic decisions.
It never equates all acquired text with a complete published paper.
"""
import copy
import hashlib
import json

from .generation import _source_blocks


def expanded_confirmation_prompt(prompt, candidates, documents, *, max_chars=60_000):
    """Expand all explicitly referenced sources atomically if the real prompt fits.

    Deduplicate repeated source contexts by explicit source references. Missing,
    conflicting or oversized acquired context retains the exact original prompt;
    the receipt describes that limit without manufacturing a support verdict.
    """
    receipt = {'status': 'not_expanded', 'original_prompt_chars': len(prompt),
               'max_prompt_chars': max_chars, 'sources': [],
               'published_paper_completeness': 'unconfirmed'}
    encoded = json.dumps(candidates, ensure_ascii=False)
    position = prompt.rfind(encoded)
    if position < 0:
        receipt['reason'] = 'candidate_serialization_not_found'
        return prompt, receipt
    by_id = {}
    for doc in documents:
        sid = int(doc.metadata['index'])
        by_id.setdefault(sid, []).append(doc)
    wanted = set()
    for candidate in candidates:
        wanted.add(int(candidate['source_id']))
        wanted.update(int(row['source_id']) for row in candidate['source_contexts'])
    registry = {}
    for sid in sorted(wanted):
        docs = by_id.get(sid, [])
        if len(docs) != 1:
            receipt['reason'] = 'missing_or_ambiguous_acquired_source'
            receipt['source_id'] = sid
            return prompt, receipt
        views = []
        _, block = next(_source_blocks(docs, '', views, complete_acquired=True))
        view, = views
        text = view['text']
        registry[str(sid)] = {
            'source_id': sid,
            'metadata': block.split('\nBEGIN SOURCE TEXT\n', 1)[0],
            'context': text,
            'context_scope': view['view_kind'],
            'published_paper_completeness': 'unconfirmed',
            'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        }
        receipt['sources'].append({'source_id': sid, 'chars': len(text),
                                   'sha256': registry[str(sid)]['text_sha256'],
                                   'view_kind': view['view_kind']})
    expanded = copy.deepcopy(candidates)
    for candidate in expanded:
        sid = int(candidate['source_id'])
        # Eligibility was checked against the earlier material. Do not replace
        # it with a different acquired version or lose that actual quoted text.
        quotes = candidate['evidence_quote']
        if isinstance(quotes, str):
            quotes = [quotes]
        if any(q not in registry[str(sid)]['context'] for q in quotes):
            receipt['reason'] = 'acquired_context_quote_mismatch'
            return prompt, receipt
        candidate['source_metadata'] = {'context_ref': str(sid), 'field': 'metadata'}
        candidate['source_context'] = {'context_ref': str(sid), 'field': 'context'}
        candidate['source_contexts'] = [
            {'source_id': row['source_id'], 'context_ref': str(row['source_id'])}
            for row in candidate['source_contexts']
        ]
    payload = {'candidates': expanded, 'source_context_registry': registry}
    serialized = json.dumps(payload, ensure_ascii=False)
    result = prompt[:position] + serialized + prompt[position + len(encoded):]
    receipt['expanded_prompt_chars'] = len(result)
    if len(result) > max_chars:
        receipt['reason'] = 'complete_acquired_context_exceeds_prompt_budget'
        return prompt, receipt
    receipt['status'] = 'expanded_complete_acquired_context'
    return result, receipt
