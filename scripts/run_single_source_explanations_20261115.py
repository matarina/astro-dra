"""Two known-source isolation diagnostics with unchanged instructions; not report correction."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from research_verify.source_explanations import explanation_prompt, parse_explanations
from scripts.experiment_error_receipt import error_receipt


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def prepare():
    from scripts.run_context_source_explanations_20261115 import prepare as context_prepare
    from research_verify.source_explanations import source_explanation_jobs
    model_name, paths, original_jobs = context_prepare()
    root = Path('evaluation/frontier-strategy-20261113')
    packet = root/'article-context-offline-20261115-v1'
    units = read(packet/'source-units-context.json')
    question = (packet/'original-question.txt').read_text()
    all_jobs = source_explanation_jobs(question,units,max_prompt_chars=160000)
    selected = [job for job in all_jobs if job['source_id'] in {3,9}]
    assert [job['source_id'] for job in selected] == [3,9]
    jobs = [dict(stage='source_explanations',arm='single_source_context',
        source_id=job['source_id'],units=job['units'],prompt=job['prompt'],blocks=job['prompt']) for job in selected]
    paths.extend([Path(__file__),Path('scripts/run_context_source_explanations_20261115.py')])
    return model_name,paths,jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--preflight', type=Path)
    parser.add_argument('--replay-attempt', type=Path)
    args = parser.parse_args()
    assert not (args.execute and args.replay_attempt)
    args.out_dir.mkdir(exist_ok=False)
    model_name, paths, jobs = prepare()
    if args.execute:
        assert args.preflight is not None
        prior = read(args.preflight / 'completion.json')
        assert prior['status'] == 'preflight_only' and prior['fresh_calls'] == 0
        assert all(sha(Path(p)) == value for p, value in read(args.preflight / 'prestart-freeze.json').items())
        paths.extend(args.preflight / name for name in ['completion.json', 'prestart-freeze.json', 'plan.json'])
    if args.replay_attempt:
        paths.extend(path for path in args.replay_attempt.glob('call-*') if path.is_file())
        paths.append(args.replay_attempt / 'calls.json')
    frozen = {str(path): sha(path) for path in paths}
    write(args.out_dir / 'prestart-freeze.json', frozen)
    for path in paths:
        resolved = path.resolve()
        try:
            repo = next(parent for parent in resolved.parents if parent.samefile(Path.cwd()))
        except StopIteration:
            continue  # Explicit external tokenizer remains hash-frozen.
        rel = resolved.relative_to(repo)
        if str(rel).startswith(('scripts/', 'local_deep_research/')):
            target = args.out_dir / 'code' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    settings = {'llm.model': model_name, 'llm.temperature': 0, 'llm.max_tokens': 12000,
                'llm.max_retries': 0, 'llm.request_timeout': 180,
                'general.enable_fact_checking': True, 'verify.enable_citation_qc': False}
    write(args.out_dir / 'plan.json', dict(scope=__doc__, maximum_fresh_calls=2,
        settings=settings, model_identity='Authorized endpoint alias only; checkpoint not verified',
        jobs=[{k: v for k, v in job.items() if k not in ['prompt', 'blocks', 'units']} for job in jobs],
        protocol='Same original question, instructions, context-enriched unit fields and sampling as historical 17-source call; each diagnostic source now gets a separate context and 12000-token output allowance. Exactly two fresh calls, sources3/9 predeclared known diagnostics, all other sources unexercised. No matched-time multi-source control, causal isolation, report, native pipeline or independent scientific assessment. Stop first failure; no retry',
        original_user_question=True, report_changes=False, new_independent_correction_credit=0))
    calls, results, failure, model = [], [], None, None
    for index, job in enumerate(jobs):
        prompt_path = args.out_dir / f'call-{index:02d}-prompt.txt'
        request_path = args.out_dir / f'call-{index:02d}-request.json'
        prompt_path.write_text(job['prompt'])
        write(request_path, job['blocks'])
        row = dict(index=index, stage=job['stage'], arm=job['arm'],
                   prompt_sha256=sha(prompt_path), request_sha256=sha(request_path), status='started')
        calls.append(row)
        try:
            if args.preflight:
                assert request_path.read_bytes() == (args.preflight / request_path.name).read_bytes()
            if args.replay_attempt:
                old = read(args.replay_attempt / 'calls.json')[index]
                assert old['status'] == 'returned'
                assert (args.replay_attempt / request_path.name).read_bytes() == request_path.read_bytes()
                response_path = args.replay_attempt / f'call-{index:02d}-response.txt'
                assert sha(response_path) == old['response_sha256']
                raw, metadata = response_path.read_text(), old['response_metadata']
                row['origin'] = 'strict_replay'
            elif args.execute:
                row['origin'] = 'fresh_model'
                write(args.out_dir / 'calls.json', calls)
                if model is None:
                    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                    from local_deep_research.config.thread_settings import settings_context
                    from local_deep_research.config.llm_config import get_llm
                    defaults = read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                    effective = apply_environment_overrides_to_snapshot({k: v.get('value') for k, v in defaults.items()}) | settings | {'llm.provider': 'openai_endpoint'}
                    with settings_context(type('Settings', (), {'username': None, 'get_setting': staticmethod(lambda k, d=None: effective.get(k, d))})()):
                        model = get_llm(settings_snapshot=effective)
                from langchain_core.messages import HumanMessage
                response = model.invoke([HumanMessage(content=job['blocks'])])
                raw, metadata = str(response.content), response.response_metadata
            else:
                row['origin'] = 'preflight_placeholder_not_reading'
                raw, metadata = json.dumps({'answers':[dict(source_id=sid,explanation='',evidence_units=[],unresolved_scope='preflight only') for sid in sorted({u['source_id'] for u in job['units']})]}), {}
            response_path = args.out_dir / f'call-{index:02d}-response.txt'
            response_path.write_text(raw)
            row.update(status='returned', response_sha256=sha(response_path), response_metadata=metadata)
            if args.execute:
                assert metadata.get('finish_reason') == 'stop'
            parsed = parse_explanations(raw, job['units'])
            results.append(dict(stage=job['stage'], arm=job['arm'], source_id=job['source_id'], parsed=parsed,
                                status='model_reading_not_semantically_verified'))
        except Exception as exc:
            failure = error_receipt(exc)
            row.update(status='unavailable', failure=failure)
            break
        finally:
            write(args.out_dir / 'calls.json', calls)
    write(args.out_dir / 'completion.json', dict(status='unavailable' if failure else ('preflight_only' if not args.execute and not args.replay_attempt else 'completed_reading_diagnostic'),
        failure=failure, fresh_calls=sum(c.get('origin') == 'fresh_model' for c in calls),
        logical_calls=len(calls), results=results,
        frozen_inputs_unchanged=all(sha(Path(p)) == value for p, value in frozen.items()),
        report_changes=0, independent_assessment_complete=False, new_independent_correction_credit=0))
    print(json.dumps(dict(logical_calls=len(calls), failure=failure, new_independent_correction_credit=0)))
    if failure:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
