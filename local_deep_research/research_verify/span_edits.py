"""Experimental model-selected subspan edits; literal preservation, not truth.

No production caller or scientific correction rules. The model writes both the
selection and replacement. Other bytes of the chosen anchor are copied rather
than asking the model to reproduce an entire flattened table row.
"""
import json

from .field_comparison import edit_prompt, parse_edits
from .request_additions import _json


def span_edit_prompt(*args):
    return (edit_prompt(*args)
        + '\nSUBSPAN REPLACEMENT PROTOCOL: For action=replace, addition contains '
          'ONLY the replacement fragment, not a rewritten anchor. Also provide '
          'replacement_span={"original_text":"exact original fragment including '
          'whitespace","occurrence":0}. occurrence is the zero-based literal '
          'occurrence within the chosen original anchor, not the complete report. '
          'Select a nonempty proper subspan containing the field you intend to '
          'correct. The program copies ALL other anchor bytes unchanged, including '
          'method names, identifiers, metrics, qualifiers and citations. Never '
          'truncate an anchor or invent offsets. Cite actual source units as '
          'before; existing anchor citations are not a certificate of support. '
          'For add, omit replacement_span and use the existing addition protocol. '
          'Whole-anchor replacement is not represented by this experimental '
          'adapter; leave it unresolved. No deletion-only replacement. This '
          'protocol preserves bytes outside the selected fragment only; it does '
          'not certify the selected fragment, replacement or whole-report quality.')


def parse_span_edits(raw, report, material, requirements, anchors, source_ids, observations):
    data = _json(raw)
    rows = data.get('proposals', [])
    if not isinstance(rows, list) or len(rows) > 3:
        raise ValueError('Subspan proposal bound')
    registry = {a['anchor_id']: a for a in anchors}
    rendered = []
    unresolved = []
    for row in rows:
        proposal = dict(row)
        if proposal.get('action') != 'replace':
            if 'replacement_span' in proposal:
                unresolved.append(dict(proposal=proposal, reason='subspan_requires_replace'))
            else:
                rendered.append(proposal)
            continue
        aid = proposal.get('anchor_id')
        spec = proposal.get('replacement_span')
        replacement = proposal.get('addition')
        if (type(aid) is not int or aid not in registry or not isinstance(spec, dict)
                or not isinstance(spec.get('original_text'), str) or not spec['original_text']
                or type(spec.get('occurrence')) is not int or spec['occurrence'] < 0
                or not isinstance(replacement, str) or not replacement.strip()):
            unresolved.append(dict(proposal=proposal, reason='invalid_model_subspan'))
            continue
        anchor = registry[aid]
        text = report[anchor['start']:anchor['end']]
        if text != anchor['text']:
            raise ValueError('Original subspan anchor changed')
        fragment = spec['original_text']
        positions = []
        start = text.find(fragment)
        while start >= 0:
            positions.append(start)
            start = text.find(fragment, start + 1)
        occurrence = spec['occurrence']
        if occurrence >= len(positions) or fragment == text:
            unresolved.append(dict(proposal=proposal, reason='unlocated_or_whole_anchor_subspan'))
            continue
        start = positions[occurrence]
        end = start + len(fragment)
        proposal['model_replacement_fragment'] = replacement
        proposal['subspan_binding'] = dict(start=anchor['start'] + start,
            end=anchor['start'] + end, original_text=fragment,
            preservation_scope='Only bytes outside this literal selection are preserved; no semantic approval')
        proposal['addition'] = text[:start] + replacement + text[end:]
        proposal['literal_anchor_after'] = proposal['addition']
        rendered.append(proposal)
    data['proposals'] = rendered
    result = parse_edits(json.dumps(data, ensure_ascii=False), report, material,
                         requirements, anchors, source_ids, observations)
    eligible = []
    for proposal in result['eligible']:
        if ('subspan_binding' in proposal
                and proposal['addition'] != proposal['literal_anchor_after']):
            unresolved.append(dict(proposal=proposal, reason='subspan_render_changed_preserved_bytes'))
        else:
            eligible.append(proposal)
    result['eligible'] = eligible
    result['unresolved'].extend(unresolved)
    return result
