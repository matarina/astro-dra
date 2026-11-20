"""Transport evidence about stage-local source views, never semantic verdicts."""
import hashlib
import json


MAX_CONTEXT_CHARS = 6000


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def capture_writer_exposure(material):
    views = getattr(material, 'views', None)
    if not isinstance(views, dict):
        return None
    records = {}
    for key, view in views.items():
        sid = int(key)
        text, block = view['text'], view['block']
        if (sid != int(view['index']) or not block or str(material).count(block) != 1
                or not block.startswith(f'[{sid}]\nTitle:')
                or 'BEGIN SOURCE TEXT\n' not in block
                or not block.split('BEGIN SOURCE TEXT\n', 1)[1].startswith(text+'\nEND SOURCE TEXT')
                or view['model_view_sha256'] != _sha(text)
                or view['model_view_chars'] != len(text)):
            raise ValueError('Writer source-view binding mismatch')
        records[str(sid)] = dict(chars=len(text), sha256=_sha(text),
                                 kind=view.get('view_kind'), scope=view.get('scope'),
                                 acquired_chars=view.get('available_chars'),
                                 acquired_sha256=view.get('available_sha256'))
    payload = dict(material_sha256=_sha(str(material)), records=records)
    return dict(payload, snapshot_sha256=_sha(_json(payload)))


def review_exposure_context(writer, material, source_ids, *, max_chars=MAX_CONTEXT_CHARS):
    if writer is not None:
        payload = {k: v for k, v in writer.items() if k != 'snapshot_sha256'}
        if _sha(_json(payload)) != writer.get('snapshot_sha256'):
            raise ValueError('Writer exposure snapshot changed')
    reviewer = capture_writer_exposure(material)
    rows = []
    texts, scopes, kinds, stages = [], [], [], []
    def reference(values, value):
        if value not in values:
            values.append(value)
        return values.index(value)
    for sid in sorted(set(map(int, source_ids))):
        key = str(sid)
        def entry(snapshot):
            if snapshot is None:
                return {'state': 'unknown'}
            record = snapshot['records'].get(key)
            if record is None:
                return {'state': 'not_in_this_stage_view'}
            acquired = (dict(chars=record['acquired_chars'], sha256=record['acquired_sha256'])
                        if record['acquired_sha256'] is not None else None)
            return dict(state='shown', text=reference(texts, dict(chars=record['chars'], sha256=record['sha256'])),
                        scope=reference(scopes, record['scope']), kind=reference(kinds, record['kind']),
                        acquired=reference(texts, acquired) if acquired is not None else None)
        rows.append(dict(source_id=sid, writer=reference(stages, entry(writer)),
                         reviewer=reference(stages, entry(reviewer))))
    payload = dict(writer_snapshot_sha256=writer.get('snapshot_sha256') if writer else None,
                   texts=texts, scopes=scopes, kinds=kinds, views=stages, source_views=rows,
                   published_paper_completeness='unconfirmed', semantic_support='not_assessed')
    prefix = ('STAGE-LOCAL SOURCE EXPOSURE (program-recorded transport, not scientific evidence):\n'
              'Writer exposure and the current reviewer excerpt can differ. A missing detail in this '
              'reviewer excerpt does not establish absence from the Writer input or the paper. '
              'Hashes/counts do not establish what a source says, article-body identity, or semantic support. '
              'A complete acquired view is not necessarily a complete published paper. '
              'Each source_views row gives Writer/reviewer indices into views. Each shown view has text/acquired '
              'indices into texts, scope into scopes and kind into kinds. Null acquired means unknown acquisition text. '
              'Equal text references mean equal bytes only. '
              'Keep unknowns explicit; obtain actual source text before making a factual correction.\n')
    context = prefix + _json(payload)
    if len(context) > max_chars:
        # Do not silently truncate rows and imply omitted records were absent.
        context = ('STAGE-LOCAL SOURCE EXPOSURE:\n'
                   'Exposure records unavailable within budget. Preserve unknown; '
                   'do not infer source absence, full-paper access or semantic support.\n'
                   + _json(dict(status='exposure_context_unavailable_budget',
                                requested_source_count=len(rows),
                                writer_snapshot_sha256=payload['writer_snapshot_sha256'])))
    if len(context) > max_chars:
        raise ValueError('Exposure context budget smaller than explicit unavailable record')
    return context
