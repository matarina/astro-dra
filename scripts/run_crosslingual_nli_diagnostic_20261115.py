"""CPU-only, saved-case NLI feasibility diagnostic; no report edits or adjudication."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir
    result = out / 'diagnostic'
    result.mkdir(exist_ok=False)
    base = Path('evaluation/frontier-strategy-20261113')
    source = base / 'segment-review-model-20261115-v2/attempt/plan.json'
    plan = json.loads(source.read_text())
    cases = plan['cases']
    # Fixed exact saved excerpt, not retrieval or a model-selected supporting quote.
    rna = cases[0]['evidence']
    start = rna.index('Human RNA sequencing (RNA-seq) data originally')
    end = rna.index('Our results show', start)
    window = rna[start:end].strip()
    pairs = [
        dict(id='rna-complete-paragraph', premise=window, hypothesis=cases[0]['parent'],
             evidence_start=start, evidence_end=start + len(window)),
        dict(id='rna-first-sentence', premise=window,
             hypothesis=cases[0]['parent'].split('。', 1)[0] + '。',
             evidence_start=start, evidence_end=start + len(window)),
        dict(id='xenium-complete-paragraph', premise=cases[1]['evidence'], hypothesis=cases[1]['parent']),
        dict(id='methods-retention-control', premise=cases[2]['evidence'], hypothesis=cases[2]['parent']),
    ]
    frozen = {str(p): digest(p) for p in [source, Path(__file__)]}
    (result / 'prestart-freeze.json').write_text(json.dumps(frozen, indent=2) + '\n')
    (result / 'pairs.json').write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + '\n')
    receipt = dict(scope='Known saved cases, not held-out, not complete-report evaluation; no independent labels',
                   device='cpu', threads=2, truncation=False, report_edits=0,
                   newly_credited_corrections=0, outputs=[])
    try:
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
        os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '45'
        import torch
        from huggingface_hub import HfApi
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        model_id = 'MoritzLaurer/mDeBERTa-v3-base-mnli-xnli'
        info = HfApi().model_info(model_id, token=False)
        receipt.update(model=model_id, revision=info.sha)
        (result / 'model-revision.json').write_text(json.dumps(dict(model=model_id, revision=info.sha), indent=2)+'\n')
        cache = str(out / 'model-cache')
        tokenizer = AutoTokenizer.from_pretrained(model_id, revision=info.sha, cache_dir=cache, token=False)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_id, revision=info.sha, cache_dir=cache, token=False, use_safetensors=True)
        torch.set_num_threads(2)
        model.to('cpu').eval()
        receipt['labels'] = model.config.id2label
        for pair in pairs:
            inputs = tokenizer(pair['premise'], pair['hypothesis'], return_tensors='pt', truncation=False)
            count = inputs['input_ids'].shape[1]
            row = dict(id=pair['id'], token_count=count)
            if count > 512:
                row['status'] = 'not_run_exceeds_512_no_truncation'
            else:
                with torch.inference_mode():
                    logits = model(**inputs).logits[0]
                    probabilities = torch.softmax(logits, dim=-1).tolist()
                row.update(status='returned', logits=logits.tolist(),
                           probabilities={model.config.id2label[i]: p for i, p in enumerate(probabilities)})
            receipt['outputs'].append(row)
        receipt['status'] = 'completed'
    except Exception as exc:
        # Exception strings may contain endpoint/proxy credentials.
        receipt.update(status='unavailable', error_type=type(exc).__name__)
    receipt['frozen_inputs_unchanged'] = all(digest(Path(p)) == h for p, h in frozen.items())
    receipt['downloaded_files'] = {str(p.relative_to(out)): digest(p)
                                   for p in (out / 'model-cache').rglob('*') if p.is_file()}
    (result / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
