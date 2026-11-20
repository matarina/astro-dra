"""Two matched complete immune Writers; only actual source-view labels change, no quality verdict."""
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
    import ast,re
    from types import SimpleNamespace
    from research_verify import generation
    from scripts.run_source_explanation_writer_pair_20261115 import writer_prompt
    root=Path('evaluation/frontier-strategy-20261113')
    prior=root/'source-explanation-writer-pair-model-20261115-v2/attempt'
    baseline_code=root/'source-view-scope-inputs-20261115-v1/baseline-code/local_deep_research/research_verify/generation.py'
    tree=ast.parse(baseline_code.read_text());scope=dict(vars(generation))
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_source_blocks']
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(baseline_code),'exec'),scope)
    casepath=root/'immune-questioned-fact-inputs-20261115-v1/case-manifest.json'
    case,=read(casepath)['cases'];pack=Path(case['source']);assert sha(pack)==case['source_sha256']
    sources=read(pack);common=(prior/'common-writer-context.txt').read_text();notes=read(prior/'source-explanations.json')
    expression=r'^\[(\d+)\]\nTitle:.*?\nEvidence type: ([^\n]+)\nBEGIN SOURCE TEXT\n(.*?)\nEND SOURCE TEXT'
    matches=list(re.finditer(expression,common,re.M|re.S));assert len(matches)==20
    replacements=[]
    for m in matches:
        sid=int(m[1]);record,=[r for r in sources if int(r['index'])==sid]
        basis=m[2].split('; complete acquired text')[0].split('; complete supplied abstract')[0]
        doc=SimpleNamespace(page_content=m[3],metadata=dict(index=sid,abstract=record.get('abstract'),evidence_type=basis))
        before_views=[];_,before=next(scope['_source_blocks']([doc],case['query'],before_views,complete_acquired=True))
        old_label=next(line for line in before.splitlines() if line.startswith('Evidence type: '))[15:]
        assert old_label==m[2] and before_views[0]['text']==m[3]
        after_views=[];_,after=next(generation._source_blocks([doc],case['query'],after_views,complete_acquired=True))
        new_label=next(line for line in after.splitlines() if line.startswith('Evidence type: '))[15:]
        assert after_views[0]['text']==m[3]
        if old_label!=new_label:
            replacements.append(dict(source_id=sid,start=m.start(2),end=m.end(2),before=old_label,after=new_label,
                source_text_sha256=__import__('hashlib').sha256(m[3].encode()).hexdigest(),
                model_view_kind=after_views[0]['view_kind']))
    assert len(replacements)==5
    changed=common
    for row in reversed(replacements):changed=changed[:row['start']]+row['after']+changed[row['end']:]
    old_blocks=[(m[1],m[3]) for m in re.finditer(expression,common,re.M|re.S)]
    assert old_blocks==[(m[1],m[3]) for m in re.finditer(expression,changed,re.M|re.S)]
    baseline=writer_prompt(common,notes);candidate=writer_prompt(changed,notes)
    assert baseline==(prior/'call-02-prompt.txt').read_text()
    budget=read(prior/'writer-token-budget.json')
    changed_ascii=sum(len(row['before'])+len(row['after']) for row in replacements)
    assert all((row['before']+row['after']).isascii() for row in replacements)
    # Prior calibrated 10% margin plus all edited ASCII characters and boundary reserve.
    upper=budget['conservative_estimated_prompt_tokens'][1]+changed_ascii+512
    assert upper+12000+8192<=131072
    guard=dict(historical_actual_prompt_tokens=96075,prior_conservative_estimate=budget['conservative_estimated_prompt_tokens'][1],
        added_edit_bound=changed_ascii+512,conservative_candidate_estimate=upper,context_limit=131072,output_tokens=12000,reserve_tokens=8192,
        tokenizer_identity_unverified=True,not_a_semantic_gate=True)
    jobs=[dict(stage='complete_writer',arm=arm,prompt=prompt,blocks=prompt,scope_changes=replacements,token_guard=guard)
          for arm,prompt in [('record_scope',baseline),('actual_view_scope',candidate)]]
    paths=[Path(__file__),Path('scripts/experiment_error_receipt.py'),Path('scripts/run_source_explanation_writer_pair_20261115.py'),
        baseline_code,casepath,pack,prior/'common-writer-context.txt',prior/'source-explanations.json',prior/'call-02-prompt.txt',
        prior/'writer-token-budget.json',*Path('local_deep_research/research_verify').glob('*.py')]
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
        protocol='Two fresh complete Writer calls on identical original immune question, nonempty draft, source paragraphs, acquired source11 body and same historical fallible17source reading notes. Only five source-view Evidence type labels change using actual formatter; old record description remains preserved in receipts, not supplied as contradictory view label. Same model/sampling/output allowance; no extra Reader/retrieval, no native pipeline or report post-edits. Baseline prompt exactly equals historical candidate call02 but is freshly sampled. Stop first failure; no retry. No correction, retention/new-error, variability or generalization verdict',
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
                raw, metadata = '# Preflight placeholder, not a generated report.', {}
            response_path = args.out_dir / f'call-{index:02d}-response.txt'
            response_path.write_text(raw)
            row.update(status='returned', response_sha256=sha(response_path), response_metadata=metadata)
            if args.execute:
                assert metadata.get('finish_reason') == 'stop'
            report_path=args.out_dir/(job['arm']+'-report.md')
            report_path.write_text(raw)
            results.append(dict(stage=job['stage'],arm=job['arm'],report_path=report_path.name,
                report_chars=len(raw),report_sha256=sha(report_path),status='writer_output_not_independently_assessed'))
        except Exception as exc:
            failure = error_receipt(exc)
            row.update(status='unavailable', failure=failure)
            break
        finally:
            write(args.out_dir / 'calls.json', calls)
    write(args.out_dir / 'completion.json', dict(status='unavailable' if failure else ('preflight_only' if not args.execute and not args.replay_attempt else 'completed_writer_scope_diagnostic'),
        failure=failure, fresh_calls=sum(c.get('origin') == 'fresh_model' for c in calls),
        logical_calls=len(calls), results=results,
        frozen_inputs_unchanged=all(sha(Path(p)) == value for p, value in frozen.items()),
        report_changes='fresh_generated_complete_reports_no_post_edits', independent_assessment_complete=False, new_independent_correction_credit=0))
    print(json.dumps(dict(logical_calls=len(calls), failure=failure, new_independent_correction_credit=0)))
    if failure:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
