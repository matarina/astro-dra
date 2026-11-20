"""Audit paired source-reader execution; preserve provisional relation concerns."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['run', 'inputs', 'out-dir']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); a.out_dir.mkdir(exist_ok=False)
    launch = read(a.run / 'launch.json')
    info = json.loads(subprocess.check_output(['docker', 'inspect', launch['container_id']]))[0]
    assert info['State']['Status'] == 'exited' and info['State']['ExitCode'] == 0
    assert info['Image'] == launch['image_id']
    assert info['HostConfig']['NetworkMode'] == 'host'
    assert info['Config']['Healthcheck']['Test'] == ['NONE']
    assert info['Config']['Entrypoint'] == ['/install/.venv/bin/python']
    reference = json.loads(subprocess.check_output(['docker', 'inspect', launch['network_reference_container']]))[0]
    overlays = lambda x: sorted((m['Source'], m['Destination'], m['RW']) for m in x['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlays(info) == overlays(reference) and len(overlays(info)) == 3
    assert all(not rw for _, _, rw in overlays(info))
    for destination in ['/workspace', str(Path.cwd())]:
        assert not next(m for m in info['Mounts'] if m['Destination'] == destination)['RW']
    attempt = a.run / 'attempt'
    for freeze in [read(a.run / 'launch-freeze.json'), read(attempt / 'prestart-freeze.json')]:
        assert all(sha(Path(filename)) == h for filename, h in freeze.items())
    for filename, h in read(attempt / 'prestart-freeze.json').items():
        if filename.startswith(('scripts/', 'local_deep_research/')):
            assert sha(attempt / 'code' / filename) == h
    completion = read(attempt / 'completion.json')
    assert completion['fresh_model_calls'] == completion['logical_calls'] == 2
    assert completion['parse_or_call_failures'] == 0 and completion['frozen_inputs_unchanged']
    assert completion['new_independent_correction_credit'] == 0 and not completion['complete_report_evaluated']
    replay = a.out_dir / 'strict-replay'
    subprocess.run([sys.executable, 'scripts/run_scope_acquisition_reader_20261115.py',
        '--inputs', str(a.inputs), '--out-dir', str(replay), '--replay-attempt', str(attempt)], check=True)
    assert read(replay / 'completion.json')['replay_exact']
    spec = read(a.inputs)
    views = [read(Path(c['views_path']))[0] for c in spec['cases']]
    assert {k: v for k, v in views[0].items() if k != 'text'} == {k: v for k, v in views[1].items() if k != 'text'}
    assert views[1]['text'].startswith(views[0]['text'] + '\n\nADDITIONAL IDENTITY-BOUND ACQUIRED ARTICLE TEXT:\n')
    calls = read(attempt / 'calls.json')
    usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    observations = []
    for c, case in zip(calls, spec['cases']):
        assert c['case_id'] == case['case_id'] and c['origin'] == 'fresh_model'
        index = c['index']; pp = attempt / f'call-{index:02d}-prompt.txt'; rp = attempt / f'call-{index:02d}-response.txt'
        assert sha(pp) == c['prompt_sha256'] and sha(rp) == c['response_sha256']
        assert len(pp.read_text()) <= 60000
        for kind in ['prompt', 'response']:
            assert (attempt / f'call-{index:02d}-{kind}.txt').read_bytes() == (replay / f'call-{index:02d}-{kind}.txt').read_bytes()
        assert c['response_metadata']['finish_reason'] == 'stop'
        for k in usage:
            usage[k] += c['response_metadata']['token_usage'][k]
        parsed = read(attempt / case['case_id'] / 'span_ids-parsed.json')
        assert parsed == read(replay / case['case_id'] / 'span_ids-parsed.json')
        source = read(Path(case['views_path']))[0]['text']
        for fact in parsed['registry'].values():
            assert fact['source_view_sha256'] == hashlib.sha256(source.encode()).hexdigest()
            assert all(source[q['start']:q['end']] == q['text'] for q in fact['quotes'])
        observations.append(dict(arm=case['case_id'], facts=parsed['registry'],
            source_view_sha256=hashlib.sha256(source.encode()).hexdigest(),
            semantic_support_verified=False))
    # Coordinator's provisional scientific diagnosis, kept out of generation.
    # Arithmetic corroborates an attribution concern; it never becomes a
    # biomedical rule, automatic report edit or independent correction score.
    write(a.out_dir / 'source-answer-observations.json', observations)
    write(a.out_dir / 'coordinator-relation-diagnosis.json', dict(
        scope='Provisional original-source comparison, not independent report adjudication.',
        population_counts=[55825, 1963, 32773, 96631], population_sum=55825+1963+32773+96631,
        platform_counts=dict(ten_x=186123, smart_seq2=1069), platform_sum=186123+1069,
        concern='Both model arms assign all population-class counts to10X although these are across-platform counts; individually present numbers do not establish their generated association.',
        affected_reader_facts=dict(abstract=['19:0'], acquired=['19:0']),
        old_view_extrapolation='Abstract arm19:2adds flow-sorting language absent from its supplied abstract; new primary methods do report FACS. Do not equate old-view absence with a false paper-level statement.',
        withdrawn_hypothesis='Do not call acquired19:1whole-blood magnetic isolation erroneous: the actual figure caption explicitly reports it.',
        quote_coverage_limit='Acquired19:2reports tetramer/CD8 double-positive gating present later in the whole view; its chosen p19/p20/p21intervals do not contain that complete gating sentence. Source-view availability differs from selected-quote coverage.',
        new_primary_evidence='CD3-positive T-cell selection is present in newly acquired own-article methods, outside the old supplied abstract.',
        report_rewrites=0, new_independent_correction_credit=0))
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q',
        'local_deep_research/tests/test_source_span_answers.py',
        'local_deep_research/tests/test_pmc_body_scope.py',
        'local_deep_research/tests/test_pubmed_evidence_acquisition.py'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (a.out_dir / 'dependency-test-output.txt').write_text(tests.stdout)
    def constructor(text):
        cls = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'PubMedSearchEngine')
        return ast.dump(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__'))
    path = 'local_deep_research/search_engine_pubmed.py'
    same = constructor(Path(path).read_text()) == constructor(subprocess.check_output(['git', 'show', 'HEAD:' + path], text=True))
    write(a.out_dir / 'test-limitations.json', dict(returncode=tests.returncode,
        direct_source_span_and_body_scope_tests='7passed', broader_pubmed_acquisition_tests='5failed',
        pubmed_constructor_AST_identical_to_HEAD=same,
        scope='Four fixture failures access a missing search_snippets_only constructor argument in unchanged HEAD constructor; one raw-abstract CitationQc expectation remains unresolved. No claim of full suite pass. Closed save-time QC not enabled or changed.'))
    assert same and tests.returncode == 1 and '5 failed, 7 passed' in tests.stdout
    write(a.out_dir / 'terminal.json', dict(container_id=launch['container_id'], exit_code=0,
        image_id=info['Image'], maximum_fresh_calls=2, actual_fresh_calls=2, usage=usage,
        original_question_unchanged=True, complete_report_evaluated=False,
        new_independent_correction_credit=0, broader_tests_all_passed=False))
    (a.out_dir / 'audit-script.py').write_bytes(Path(__file__).read_bytes())
    files = [f for root in [a.run, a.inputs.parent, a.out_dir] for f in root.rglob('*') if f.is_file()]
    payload = {str(f): sha(f) for f in sorted(set(files))}
    write(a.out_dir / 'MANIFEST.json', payload)
    assert all(sha(Path(f)) == h for f, h in payload.items())
    write(a.out_dir / 'completion.json', dict(status='execution_provenance_audit_passed_with_explicit_test_limitations',
        payloads=len(payload), manifest_sha256=sha(a.out_dir / 'MANIFEST.json'), audit_fresh_calls=0,
        broader_tests_all_passed=False, new_independent_correction_credit=0))
    print((a.out_dir / 'completion.json').read_text())


if __name__ == '__main__':
    main()
