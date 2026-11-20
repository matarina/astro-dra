"""Matched known IF source-field reading; single versus multiple requirement associations, no report score."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from research_verify.canonical_fields import unit_field_prompt, parse_unit_fields
from research_verify.request_additions import parse_request_plan
from scripts.experiment_error_receipt import error_receipt


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def prepare():
    root=Path('evaluation/frontier-strategy-20261113')
    prior=root/'request-canonical-if-model-20261114-v1/attempt'
    casepath=root/'source-span-if-original-inputs-20261115-v1/case-manifest.json'
    case,=read(casepath)['cases'];pack=Path(case['source']);assert sha(pack)==case['source_sha256']
    record,=[s for s in read(pack) if str(s['index'])=='5']
    assert hashlib.sha256(record['fetched_content'].encode()).hexdigest()=='00777763544bc2049b0e4d9777dac8c956608c0a5f00ba96e6c8cf4966be2787'
    units=read(prior/'source-units.json');assert len(units)==283 and {u['source_id'] for u in units}=={5}
    for u in units:
        assert hashlib.sha256(u['text'].encode()).hexdigest()==u['text_sha256']
        if u['kind']=='text':assert record['fetched_content'][u['start']:u['end']]==u['text']
    requirements=parse_request_plan((prior/'call-00-response.txt').read_text(),case['query'])
    baseline=unit_field_prompt(case['query'],requirements,units);assert baseline==(prior/'call-01-prompt.txt').read_text()
    candidate=unit_field_prompt(case['query'],requirements,units,multi_requirement=True)
    old_usage=read(prior/'calls.json')[1]['response_metadata']['token_usage']['prompt_tokens']
    # Historical byte-identical baseline calibration, 10% reserve plus every
    # added/removed ASCII character as an extra token and boundary reserve.
    extra=len(candidate)-len(baseline)+1000
    conservative=int(old_usage*1.1)+extra
    assert conservative+12000+8192<=131072
    jobs=[dict(stage='report_blind_canonical_fields',arm=arm,source_id=5,units=units,
               requirements=requirements,prompt=prompt,blocks=prompt,
               conservative_input_tokens=conservative,multi_requirement=multi)
          for arm,prompt,multi in [('single_requirement',baseline,False),('multiple_requirements',candidate,True)]]
    paths=[Path(__file__),Path('scripts/experiment_error_receipt.py'),casepath,pack,
           prior/'source-units.json',prior/'call-00-response.txt',prior/'call-01-prompt.txt',prior/'calls.json',
           *Path('local_deep_research/research_verify').glob('*.py')]
    return 'deepseek-v4-flash',paths,jobs


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
        protocol='Two fresh source-only calls, same original full Chinese IF request, source5 complete acquired text and identical283canonical units, same12-field/output/model budgets. Baseline prompt byte-exact historical canonical field reader. Candidate uses plural requirement_ids and a generic association instruction, so one factual observation can address multiple explicit criteria without duplicate rows. No report, feedback, expected counts or gold supplied. Generated field bindings are fallible, not independent assessment; one known source does not exercise20-paper eligibility/count task. No Writer/native/retrieval/report edit; stop first failure, no retry',
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
                raw, metadata = json.dumps({'sources':[dict(source_id=sid,fields=[],unresolved_requirements=[r['requirement_id'] for r in job['requirements']]) for sid in sorted({u['source_id'] for u in job['units']})]}), {}
            response_path = args.out_dir / f'call-{index:02d}-response.txt'
            response_path.write_text(raw)
            row.update(status='returned', response_sha256=sha(response_path), response_metadata=metadata)
            if args.execute:
                assert metadata.get('finish_reason') == 'stop'
            parsed = parse_unit_fields(raw, job['requirements'], job['units'], multi_requirement=job['multi_requirement'])
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
