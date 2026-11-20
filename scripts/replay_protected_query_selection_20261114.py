"""Offline frozen formatter comparison; no model, retrieval or report edits."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from research_verify import generation
from scripts.prepare_source_detail_material_20261114 import native_documents


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(exist_ok=False)
    base = Path('evaluation/frontier-strategy-20261113')
    manifest = base / 'fragment-revision-primary-inputs-20261114-v2/case-manifest.json'
    frozen_path = base / 'adipose-revision-primary-live-20261114-v1/acquisition/code/local_deep_research/research_verify/generation.py'
    spec = importlib.util.spec_from_file_location('research_verify._frozen_generation', frozen_path)
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    cases = json.loads(manifest.read_text())['cases']
    cases[1]['source'] = str(base / 'adipose-revision-primary-live-20261114-v1/acquisition/sources.json')
    paths = [manifest, frozen_path, Path(__file__), Path(generation.__file__),
             Path('scripts/prepare_source_detail_material_20261114.py'),
             *Path('local_deep_research/research_verify').glob('*.py')]
    paths += [Path(c[k]) for c in cases for k in ('source', 'draft')]
    freeze = {str(p): sha(p) for p in paths}
    (args.out_dir / 'prestart-freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    for p in [Path(__file__), Path(generation.__file__)]:
        dest = args.out_dir / 'code' / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    results = []
    for case in cases:
        dest = args.out_dir / case['case_id']
        dest.mkdir()
        sources = json.loads(Path(case['source']).read_text())
        docs = native_documents(sources)
        question = case['query']
        report = Path(case['draft']).read_text()
        assert hashlib.sha256(report.encode()).hexdigest() == case['draft_sha256']
        extended = generation.writer_source_query(question, report, claim_directed=True)
        common = dict(max_chars=200000, required_ids={int(s['index']) for s in sources})
        baseline = generation.format_source_documents(docs, question, **common)
        old_extended = generation.format_source_documents(docs, extended, **common)
        assert str(baseline) == str(frozen.format_source_documents(docs, question, **common))
        assert str(old_extended) == str(frozen.format_source_documents(docs, extended, **common))
        receipts = []
        candidate = generation.format_source_documents(
            docs, extended, protected_query=question, selection_receipts=receipts, **common)
        assert set(candidate.views) == set(baseline.views) == common['required_ids']
        assert len(candidate) <= common['max_chars']
        retained = 0
        for doc in docs:
            sid = int(doc.metadata['index'])
            assert baseline.views[sid]['available_sha256'] == candidate.views[sid]['available_sha256']
            abstract = doc.metadata.get('abstract') or ''
            if abstract:
                assert abstract in candidate.views[sid]['text']
            if baseline.views[sid]['view_kind'] == 'complete_acquired_text':
                assert baseline.views[sid]['text'] == candidate.views[sid]['text']
                continue
            text = doc.page_content.replace(abstract, '', 1).strip() if abstract else doc.page_content
            if not text:
                continue
            if len(text) <= 6000:
                assert text in candidate.views[sid]['text']
                continue
            windows = generation.retrieve_passages(
                text, question, window_chars=2000, max_passages=3, overlap_chars=200)
            for window in windows:
                assert text[window.start:window.end] == window.text
                assert window.text in candidate.views[sid]['text']
                retained += 1
        for name, material in [('question-only', baseline), ('draft-expanded', old_extended),
                               ('protected', candidate)]:
            (dest / (name + '-material.txt')).write_text(str(material))
        (dest / 'selection-receipts.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + '\n')
        row = dict(case_id=case['case_id'],sources=len(sources),source_input_sha256=sha(Path(case['source'])),
                   report_input_sha256=case['draft_sha256'],baseline_default_bytes_unchanged=True,
                   extended_default_bytes_unchanged=True,all_request_windows_retained=True,
                   protected_window_count=retained,material_chars=dict(question_only=len(baseline),
                   draft_expanded=len(old_extended),protected=len(candidate)),
                   scientific_status='not_assessed')
        if case['case_id'] == 'original-adipose':
            body = next(s['fetched_content'] for s in sources if s['index'] == '2')
            method = next(p for p in body.split('\n\n') if p.startswith('Adipose tissue samples (n=36)'))
            (dest / 'known-primary-method-control.txt').write_text(method)
            row['known_method_control'] = {name: method in material.views[2]['text']
                for name, material in [('question_only',baseline),('draft_expanded',old_extended),('protected',candidate)]}
            assert row['known_method_control'] == dict(question_only=True,draft_expanded=False,protected=True)
        results.append(row)
    assert all(sha(Path(p)) == digest for p,digest in freeze.items())
    result = dict(scope='Offline request-window retention under matched 200000-character source budget; not end-to-end report evaluation',
                  results=results,launch_start_end_hashes_match=True,model_calls=0,network_calls=0,
                  report_modifications=0,quality_claim=None,newly_credited_corrections=0,
                  limits='Protection preserves baseline retrieval bytes, not semantic usefulness. Optional semantic ranking can incur two ranking invocations; no such calls made here. No production caller/activation.')
    (args.out_dir / 'completion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
