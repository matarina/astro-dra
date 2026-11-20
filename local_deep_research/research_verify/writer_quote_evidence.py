"""Carry exact same-source Writer quotations to review, without approving claims.

For an opt-in serialized-report experiment. Matching generated text identifies
transport provenance, never entailment, usefulness or source authenticity.
"""
import copy
import hashlib
import json

from .generation import SourceMaterial
from .material_exposure import capture_writer_exposure


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def carry_writer_quotes(writer, reviewer, report, registry, rendering, claims, *, context_chars=400):
    if type(context_chars) is not int or context_chars < 0:
        raise ValueError('Context must be a nonnegative character count')
    if capture_writer_exposure(writer) is None or capture_writer_exposure(reviewer) is None:
        raise ValueError('Bound source-view registries required')
    rows, rejected, windows = [], [], {}
    for item in rendering['facts']:
        fid = item['fact_id']
        fact = registry.get(fid)
        if not fact:
            rejected.append(dict(fact_id=fid, reason='missing_registry_fact'))
            continue
        relevant = [c for c in claims if fact['text'] in c['text']
                    and int(fact['source_id']) in c['source_ids']]
        if not relevant:
            continue
        sid = int(fact['source_id'])
        view = writer.views.get(sid)
        a, b = item['start'], item['end']
        expected = fact['text'] + ' [' + str(sid) + ']'
        if (not view or str(item['source_id']) != str(sid)
                or type(a) is not int or type(b) is not int or not 0 <= a < b <= len(report)
                or report[a:b] != expected or item['rendered'] != expected
                or fact['source_view_sha256'] != view['model_view_sha256']
                or item['fact_sha256'] != digest(json.dumps(fact, ensure_ascii=False, sort_keys=True))):
            rejected.append(dict(fact_id=fid, reason='report_fact_source_binding_mismatch'))
            continue
        for quote in fact['quotes']:
            start, end, text = quote['start'], quote['end'], quote['text']
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(view['text']) or view['text'][start:end] != text):
                rejected.append(dict(fact_id=fid, reason='quote_coordinate_mismatch'))
                continue
            target = reviewer.views.get(sid)
            status = ('review_source_absent' if target is None else
                      'review_source_binding_changed' if target.get('available_sha256') is not None
                      and target['available_sha256'] != view['available_sha256'] else
                      'already_present' if text in target['text'] else 'needs_window')
            row = dict(fact_id=fid, source_id=sid, claim_ids=[c['claim_id'] for c in relevant],
                       quote_start=start, quote_end=end, quote=text, quote_sha256=digest(text),
                       writer_view_sha256=view['model_view_sha256'], status=status)
            rows.append(row)
            if status == 'needs_window':
                lo, hi = max(0, start-context_chars), min(len(view['text']), end+context_chars)
                windows.setdefault(sid, []).append((lo, hi))
    output = str(reviewer)
    views = copy.deepcopy(reviewer.views)
    additions = []
    for sid, intervals in windows.items():
        merged = []
        for a, b in sorted(intervals):
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        text = views[sid]['text']
        for a, b in merged:
            original = writer.views[sid]['text'][a:b]
            text += (f'\n\nADDITIONAL SAME-SOURCE WRITER EVIDENCE WINDOW '
                     f'(original characters {a}:{b}; excerpt, not semantic verification):\n' + original)
            additions.append(dict(source_id=sid, start=a, end=b, text=original,
                                  text_sha256=digest(original)))
        view = views[sid]
        old = view['block']
        marker = 'BEGIN SOURCE TEXT\n' + view['text'] + '\nEND SOURCE TEXT'
        assert old.count(marker) == 1 and output.count(old) == 1
        block = old.replace(marker, 'BEGIN SOURCE TEXT\n'+text+'\nEND SOURCE TEXT', 1)
        output = output.replace(old, block, 1)
        view.update(block=block, text=text, model_view_chars=len(text), model_view_sha256=digest(text),
                    view_kind='reviewer_text_with_bound_writer_windows',
                    scope=str(view.get('scope') or '')+'; original same-source Writer windows attached')
    result = SourceMaterial(output, views)
    capture_writer_exposure(result)
    for row in rows:
        if row['status'] == 'needs_window':
            assert row['quote'] in result.views[row['source_id']]['text']
            row['status'] = 'window_attached'
    return result, dict(quote_bindings=rows, rejected_bindings=rejected, additions=additions,
                        original_review_material_sha256=digest(str(reviewer)),
                        new_review_material_sha256=digest(str(result)),
                        original_review_text_preserved=True, semantic_verification='not_performed',
                        report_modified=False)
