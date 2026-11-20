"""One Writer-only header ablation; every supplied scientific text stays exact."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.section_document import render
from research_verify.pmc_identity import article_text, _doi
from scripts.experiment_error_receipt import error_receipt


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, default=str) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior-writer', type=Path, required=True)
    p.add_argument('--source-views', type=Path, required=True)
    p.add_argument('--bindings', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--replay-attempt', type=Path)
    a = p.parse_args()
    assert not (a.execute and a.replay_attempt)
    a.out_dir.mkdir(exist_ok=False)
    prior = a.prior_writer
    oldplan = json.loads((prior / 'plan.json').read_text())
    oldresult = json.loads((prior / 'result.json').read_text())
    sources = json.loads((prior / 'sources.json').read_text())
    registry = json.loads((prior / 'fact-registry.json').read_text())
    oldprompt = (prior / 'prompt.txt').read_text()
    assert sha(prior / 'prompt.txt') == oldresult['prompt_sha256']
    assert sha(prior / 'response.txt') == oldresult['response_sha256']
    baseline, receipt = render((prior / 'response.txt').read_text(), sources, registry)
    assert baseline == (prior / 'candidate-draft.txt').read_text()
    views = json.loads(a.source_views.read_text())
    bindings = json.loads(a.bindings.read_text())['bindings']
    by_id = {str(s['index']): s for s in sources}
    prompt = oldprompt
    changes = []
    for binding in bindings:
        sid = binding['source_id']
        own = binding['own_article_ids']
        source = by_id[sid]
        assert str(source['pmid']) == own['pmid'] and _doi(source['doi']) == _doi(own['doi'])
        xml = Path(binding['xml_path'])
        assert sha(xml) == binding['xml_sha256']
        body = article_text(xml.read_text(), {'pmcid': own['pmcid'], 'doi': own['doi']},
                            pmid=own['pmid'], require_body=True)
        assert body and digest(body) == binding['body_sha256']
        view = views[sid]
        assert body in view['text'] and digest(view['text']) == view['model_view_sha256']
        block = view['block']
        assert prompt.count(block) == 1
        header, scientific = block.split('BEGIN SOURCE TEXT\n', 1)
        lines = header.splitlines(keepends=True)
        positions = [i for i, line in enumerate(lines) if line.startswith('Evidence type: ')]
        assert len(positions) == 1
        i = positions[0]
        before = lines[i]
        after = ('Evidence type: supplied text includes an identity-bound acquired article body; '
                 'only the supplied text is available; published-paper and supplement completeness unconfirmed\n')
        lines[i] = after
        newblock = ''.join(lines) + 'BEGIN SOURCE TEXT\n' + scientific
        assert newblock.split('BEGIN SOURCE TEXT\n', 1)[1] == scientific
        changes.append(dict(source_id=sid, before=before, after=after,
                            old_block_sha256=digest(block), new_block_sha256=digest(newblock),
                            source_text_sha256=view['model_view_sha256'], body_sha256=digest(body),
                            xml_sha256=sha(xml)))
        prompt = prompt.replace(block, newblock, 1)
    # Reverse exactly the four source-bound header edits, then compare ALL bytes.
    reversed_prompt = prompt
    for change in reversed(changes):
        # All replacement headers are identical; locate the source's full block.
        block = views[change['source_id']]['block']
        newblock = block.replace(change['before'], change['after'], 1)
        assert reversed_prompt.count(newblock) == 1
        reversed_prompt = reversed_prompt.replace(newblock, block, 1)
    assert reversed_prompt == oldprompt and len(prompt) < 500000
    files = [Path(__file__), Path('scripts/experiment_error_receipt.py'), a.source_views, a.bindings,
             *[Path(b['xml_path']) for b in bindings],
             *[prior / f for f in ['plan.json', 'result.json', 'prompt.txt', 'response.txt',
                                  'sources.json', 'fact-registry.json', 'candidate-draft.txt']],
             *Path('local_deep_research/research_verify').glob('*.py')]
    frozen = {str(f): sha(f) for f in files}
    write(a.out_dir / 'prestart-freeze.json', frozen)
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            target = a.out_dir / 'code' / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    (a.out_dir / 'baseline.txt').write_text(baseline)
    (a.out_dir / 'prompt.txt').write_text(prompt)
    write(a.out_dir / 'changes.json', changes)
    plan = dict(scope='Writer-stage only; four verified source-bound access headers changed. '
                     'Original question/nonempty draft/source text/reader notes/fact registry/output interface exact. '
                     'Not a full native-checked report or independent assessment.',
                prior_writer=str(prior), query=oldplan['query'], settings=oldplan['settings'],
                maximum_fresh_calls=1, native_consistency_configured=True, native_check_executed=False,
                all_non_header_prompt_bytes_exact=True, independent_correction_credit=0)
    write(a.out_dir / 'plan.json', plan)
    result = dict(status='started', prompt_sha256=sha(a.out_dir / 'prompt.txt'))
    write(a.out_dir / 'result.json', result)
    try:
        if a.replay_attempt:
            previous = json.loads((a.replay_attempt / 'result.json').read_text())
            assert previous['prompt_sha256'] == result['prompt_sha256']
            assert prompt == (a.replay_attempt / 'prompt.txt').read_text()
            assert sha(a.replay_attempt / 'response.txt') == previous['response_sha256']
            raw = (a.replay_attempt / 'response.txt').read_text()
            metadata = previous['response_metadata']
            origin = 'saved_response_replay'
        elif a.execute:
            from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
            from local_deep_research.config.thread_settings import settings_context
            from local_deep_research.config.llm_config import get_llm
            defaults = json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
            settings = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()}) | plan['settings'] | {'llm.provider': 'openai_endpoint', 'llm.request_timeout': 180}
            with settings_context(type('Settings', (), {'username': None, 'get_setting': staticmethod(lambda k, d=None: settings.get(k, d))})()):
                model = get_llm(settings_snapshot=settings)
            response = model.invoke(prompt)
            raw, metadata, origin = str(response.content), response.response_metadata, 'fresh_model'
        else:
            raw = (prior / 'response.txt').read_text()
            metadata, origin = {}, 'preflight_saved_baseline_placeholder'
        (a.out_dir / 'response.txt').write_text(raw)
        result.update(response_sha256=sha(a.out_dir / 'response.txt'), response_metadata=metadata, origin=origin)
        write(a.out_dir / 'result.json', result)
        draft, receipt = render(raw, sources, registry)
        (a.out_dir / 'candidate-draft.txt').write_text(draft)
        write(a.out_dir / 'rendering.json', receipt)
        if a.replay_attempt:
            assert draft == (a.replay_attempt / 'candidate-draft.txt').read_text()
            assert receipt == json.loads((a.replay_attempt / 'rendering.json').read_text())
        result.update(status='draft_generated', draft_chars=len(draft), draft_sha256=sha(a.out_dir / 'candidate-draft.txt'), replay_exact=bool(a.replay_attempt))
    except Exception as exc:
        result.update(status='unavailable', failure=error_receipt(exc))
    result.update(frozen_inputs_unchanged=all(sha(Path(f)) == h for f, h in frozen.items()),
                  independent_correction_credit=0, native_check_executed=False)
    write(a.out_dir / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'response_metadata'}))
    if result['status'] == 'unavailable':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
