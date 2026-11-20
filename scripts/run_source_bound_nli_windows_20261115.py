"""Offline CPU NLI source-window diagnosis; preserves complete claims, no edits."""
import argparse
import hashlib
import json
import os
import sys
import types
from pathlib import Path

# This standalone CPU diagnostic needs only pure text modules, not the web
# application's settings/http imports in research_verify.__init__. Load those
# exact files under a private package namespace; production imports are untouched.
_pure = types.ModuleType('_nli_diagnostic_text')
_pure.__path__ = [str(Path('local_deep_research/research_verify').resolve())]
sys.modules[_pure.__name__] = _pure
from _nli_diagnostic_text.nli_windows import source_windows


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(exist_ok=False)
    base = Path('evaluation/frontier-strategy-20261113')
    old = base / 'crosslingual-nli-diagnostic-20261115-v1'
    paths = [Path(__file__), Path('local_deep_research/research_verify/nli_windows.py'),
             Path('local_deep_research/research_verify/claims.py'),
             Path('local_deep_research/research_verify/report_syntax.py'),
             base / 'segment-review-model-20261115-v2/attempt/plan.json',
             base / 'cell-pii-identity-live-20261115-v2/attempt/report-01/sources.json',
             base / 'cell-pii-identity-live-20261115-v2/attempt/report-04/sources.json',
             base / 'fragment-revision-model-20261114-v2/attempt/original-adipose/original-report.txt',
             old / 'diagnostic/receipt.json', old / 'python-environment.txt',
             base / 'source-bound-nli-window-inputs-20261115-v1/adipose-claim.json']
    freeze = {str(p): sha(p) for p in paths}
    (out / 'prestart-freeze.json').write_text(json.dumps(freeze, indent=2)+'\n')
    for p in paths[:4]:
        dest = out / 'code' / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    cases = json.loads(paths[4].read_text())['cases']
    xeno = {s['index']: s for s in json.loads(paths[5].read_text())}
    adipose = {s['index']: s for s in json.loads(paths[6].read_text())}
    rna_material = cases[0]['evidence']
    pos = rna_material.index('[81]\nTitle:')
    body = rna_material.index('BEGIN SOURCE TEXT\n', pos)+len('BEGIN SOURCE TEXT\n')
    end = rna_material.index('\nEND SOURCE TEXT', body)
    rna_prefix, rna_text = rna_material[pos:body], rna_material[body:end]
    jobs = []

    def add(case_id, claim, source_id, source, text, scope):
        prefix = ('SOURCE '+source_id+'\nTitle: '+str(source.get('title') or '')+
                  '\nJournal: '+str(source.get('journal') or '')+
                  '\nDate: '+str(source.get('pubdate') or source.get('publication_year') or '')+
                  '\nSOURCE TEXT:\n')
        jobs.append(dict(case_id=case_id, claim=claim, source_id=source_id,
                         prefix=prefix, source_text=text, scope=scope))

    for suffix, claim in [('paragraph', cases[0]['parent']),
                          ('first-sentence', cases[0]['parent'].split('。', 1)[0]+'。')]:
        jobs.append(dict(case_id='rna-'+suffix, claim=claim, source_id='81',
                         prefix=rna_prefix, source_text=rna_text,
                         scope='Exact entire source81 view in actual saved native first-check request, including header'))
    for sid in ['2', '9']:
        # Reuse the EXACT previously supplied abstract, now source-scoped and
        # with actual bound metadata; this explicitly changes prior probe input.
        marker = '['+sid+']\n'
        material = cases[1]['evidence']
        start = material.index(marker)+len(marker)
        stop = material.find('\n[', start)
        text = material[start:] if stop < 0 else material[start:stop]
        add('xenium-complete-'+sid, cases[1]['parent'], sid, xeno[sid], text,
            'Previously supplied source2/9 abstract, exact text; actual metadata added from latest authenticated sourcepack')
    add('methods-retention-control', cases[2]['parent'], '1', xeno['1'],
        cases[2]['evidence'].removeprefix('[1]\n'), 'Exact known Methods retention control, no new gold')
    report = paths[7].read_text()
    fixture = json.loads(paths[10].read_text())
    assert sha(paths[7]) == fixture['source_sha256']
    compound = fixture['claim']
    assert report[compound['report_start']:compound['report_end']] == compound['text']
    for sid in ['2', '3']:
        source = adipose[sid]
        text = source.get('fetched_content') or source.get('source_material') or source.get('abstract') or ''
        add('adipose-complete-'+sid, compound['text'], sid, source, text,
            'Complete actual two-source report statement; each source scored separately, no union-of-support verdict')
    (out / 'inputs.json').write_text(json.dumps(jobs, ensure_ascii=False, indent=2)+'\n')
    receipt = dict(scope='Known cases across three archive tasks; NOT heldout, matched algorithm-quality comparison or whole-report adjudication',
                   max_tokens=512, overlap_chars=160, max_windows_per_source=128,
                   maximum_predictions=200, truncation=False, global_semantic_verdict=None,
                   report_changes=0, new_independent_correction_credit=0, results=[])
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import torch
    import requests
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    blocked_http = []

    def reject_http(*_args, **_kwargs):
        blocked_http.append('blocked')
        raise RuntimeError('Network request forbidden during offline diagnostic')

    requests.sessions.Session.request = reject_http
    model_record = json.loads(paths[8].read_text())
    for p, h in model_record['downloaded_files'].items():
        assert sha(old / p) == h
    receipt['model'] = model_record['model']
    receipt['revision'] = model_record['revision']
    snapshot = old / 'model-cache' / ('models--'+model_record['model'].replace('/', '--')) / 'snapshots' / model_record['revision']
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    count = lambda p, h: len(tokenizer(p, h, truncation=False)['input_ids'])
    planned = []
    for job in jobs:
        view = source_windows(job['source_text'], job['claim'], job['prefix'], count,
                              max_tokens=512, overlap_chars=160, max_windows=128)
        planned.append(dict(case_id=job['case_id'], source_id=job['source_id'], view=view))
    (out / 'window-plan.json').write_text(json.dumps(planned, ensure_ascii=False, indent=2)+'\n')
    total = sum(len(p['view']['windows']) for p in planned)
    receipt['planned_windows'] = total
    assert total <= 200, 'Predeclared total prediction cap exceeded; no model loaded'
    model = None
    if args.execute:
        torch.set_num_threads(2)
        model = AutoModelForSequenceClassification.from_pretrained(
            str(snapshot), local_files_only=True, use_safetensors=True).to('cpu').eval()
        receipt['labels'] = model.config.id2label
    for row in planned:
        output = dict(case_id=row['case_id'], source_id=row['source_id'],
                      coverage_status=row['view']['status'],
                      text_coverage_complete=row['view']['text_coverage_complete'], windows=[])
        for i, w in enumerate(row['view']['windows']):
            item = dict(index=i, start=w['start'], end=w['end'], tokens=w['tokens'])
            if model is not None:
                inputs = tokenizer(w['premise'], row['view']['complete_hypothesis'],
                                   return_tensors='pt', truncation=False)
                assert inputs['input_ids'].shape[1] == w['tokens'] <= 512
                with torch.inference_mode():
                    logits = model(**inputs).logits[0]
                    probs = torch.softmax(logits, dim=-1).tolist()
                item.update(logits=logits.tolist(), probabilities={model.config.id2label[j]:v for j,v in enumerate(probs)})
            output['windows'].append(item)
        receipt['results'].append(output)
        (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    receipt.update(status='completed' if args.execute else 'preflight_no_predictions',
                   model_predictions=total if args.execute else 0,
                   frozen_inputs_unchanged=all(sha(Path(p)) == h for p,h in freeze.items()),
                   model_files_unchanged=all(sha(old / p) == h for p,h in model_record['downloaded_files'].items()),
                   network_reads=0, blocked_http_attempts=len(blocked_http))
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
