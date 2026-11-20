"""Offline payload/coverage audit; never produces an overall semantic verdict."""
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    base = Path('evaluation/frontier-strategy-20261113')
    old = base / 'crosslingual-nli-diagnostic-20261115-v1'
    run = base / 'source-bound-nli-windows-model-20261115-v1'
    preflight = base / 'source-bound-nli-windows-preflight-20261115-v4'
    out = base / 'source-bound-nli-windows-terminal-audit-20261115-v1'
    out.mkdir(exist_ok=False)
    inputs = json.loads((run/'inputs.json').read_text())
    plan = json.loads((run/'window-plan.json').read_text())
    receipt = json.loads((run/'receipt.json').read_text())
    frozen = json.loads((run/'prestart-freeze.json').read_text())
    assert receipt['status'] == 'completed'
    assert receipt['blocked_http_attempts'] == 0
    assert all(sha(Path(p)) == h for p,h in frozen.items())
    assert sha(run/'window-plan.json') == sha(preflight/'window-plan.json')
    assert sha(run/'inputs.json') == sha(preflight/'inputs.json')
    model_record = json.loads((old/'diagnostic/receipt.json').read_text())
    assert all(sha(old/p) == h for p,h in model_record['downloaded_files'].items())
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import requests
    attempts = []

    def reject(*args, **kwargs):
        attempts.append('blocked')
        raise RuntimeError('Audit is offline')

    requests.sessions.Session.request = reject
    from transformers import AutoTokenizer
    snapshot = old/'model-cache'/('models--'+model_record['model'].replace('/', '--'))/'snapshots'/model_record['revision']
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    checks = []
    assert len(inputs) == len(plan) == len(receipt['results']) == 7
    for original, planned, returned in zip(inputs, plan, receipt['results']):
        assert original['case_id'] == planned['case_id'] == returned['case_id']
        view = planned['view']
        assert view['complete_hypothesis'] == original['claim']
        text = original['source_text']
        assert hashlib.sha256(text.encode()).hexdigest() == view['source_sha256']
        assert view['text_coverage_complete'] and returned['text_coverage_complete']
        covered_end = 0
        assert len(view['windows']) == len(returned['windows'])
        for w, prediction in zip(view['windows'], returned['windows']):
            assert 0 <= w['start'] <= covered_end < w['end'] <= len(text)
            assert w['text'] == text[w['start']:w['end']]
            assert w['premise'] == original['prefix'] + w['text']
            count = len(tokenizer(w['premise'], original['claim'], truncation=False)['input_ids'])
            assert count == w['tokens'] == prediction['tokens'] <= 512
            assert (w['start'],w['end']) == (prediction['start'],prediction['end'])
            p = prediction['probabilities']
            assert set(p) == {'entailment','neutral','contradiction'}
            assert all(0 <= v <= 1 for v in p.values()) and abs(sum(p.values())-1) < 1e-6
            covered_end = w['end']
        assert covered_end == len(text)
        checks.append(dict(case_id=original['case_id'], source_chars=len(text),
                           windows=len(view['windows']), complete_text_exposure=True,
                           semantic_completeness_proven=False))
    assert sum(r['windows'] for r in checks) == receipt['model_predictions'] == 70
    assert not attempts
    audit = dict(status='payload_and_exposure_checks_pass', checks=checks,
                 exact_preflight_match=True, frozen_code_inputs_model_match=True,
                 additional_model_predictions=0, http_attempts=0,
                 scientific_verdict=None, independent_correction_credit=0,
                 limit='Exposure and numerical probabilities do not prove cross-window reasoning, support, retention, or full-report correction')
    (out/'terminal-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    payloads = [*run.rglob('*.json'), *run.rglob('*.py'),
                preflight/'receipt.json', *base.glob('source-bound-nli-windows-preflight-*/failure.*'),
                Path(__file__), out/'terminal-audit.json']
    manifest = {str(p): sha(p) for p in payloads}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False))


if __name__ == '__main__':
    main()
