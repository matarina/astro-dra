"""Three-call known-task experiment: source-only explanations and paired complete Writers.

Both Writers see identical original prefix, selected original units and newly
acquired primary body. Only the candidate gets new fallible explanatory notes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from research_verify.source_explanations import explanation_prompt, parse_explanations
from scripts.experiment_error_receipt import error_receipt
from scripts.run_canonical_immune_writer_quotes_20261115 import prepare as original_prepare


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value): p.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def prepare():
    paths, case, requirements, allunits, batches, prefix = original_prepare()
    root = Path('evaluation/frontier-strategy-20261113')
    selected_path = root / 'canonical-immune-writer-quotes-model-20261115-v1/attempt/writer-field-transport.json'
    selected = read(selected_path)
    registry = {(u['source_id'], u['unit_id']): u for u in allunits}
    for unit in selected:
        original = registry[unit['source_id'], unit['unit_id']]
        assert all(unit[k] == original[k] for k in original)
    primary = root / 'native-source11-cloud-methods-followup-20261115-v1'
    acquisition = root / 'native-source11-cloud-primary-acquisition-20261115-v1'
    bodypath = primary / 'article-text.txt'
    result = read(acquisition / 'result.json')
    assert result['status'] == 'acquired_identity_bound_xml'
    record, = [r for r in read(paths['source']) if str(r['index']) == '11']
    assert result['own_ids'] == {k: record[k] for k in ['pmid', 'pmcid', 'doi']}
    assert sha(bodypath) == read(primary / 'coordinator-reading.json')['new_body_sha256']
    for receipt in result['requests']:
        if receipt['final_url'].endswith('.xml'):
            assert receipt['http_status'] == 200 and receipt['md5'] == receipt['expected_md5']
            assert sha(acquisition / 'PMC10195816.1.xml') == receipt['sha256']
    units = [{**u, 'material_id': 'historical_selected_original'} for u in selected]
    body = bodypath.read_text()
    for index, match in enumerate(re.finditer(r'\S[\s\S]*?(?=\n[ \t]*\n|\Z)', body)):
        units.append(dict(material_id='new_primary_' + sha(bodypath), source_id=11,
            unit_id=index, kind='text', start=match.start(), end=match.end(),
            text=match[0], text_sha256=hashlib.sha256(match[0].encode()).hexdigest()))
    for unit in selected:
        assert unit['text'] in paths['material'].read_text() and paths['material'].read_text() in prefix
    common = prefix + '\nNEW PRIMARY BODY FOR EXISTING SOURCE (IDENTICAL BOTH ARMS):\n' + json.dumps({k:record[k] for k in ['index','pmid','pmcid','doi']},ensure_ascii=False) + '\n' + body
    # All historical selected original paragraphs remain in their original
    # source blocks. Do not append another copy of those already visible bytes.
    reader = explanation_prompt(case['query'], units)
    assert len(reader) <= 180000 and len(common) <= 460000
    paths.update(selected=selected_path, primary_body=bodypath,
        primary_xml=acquisition/'PMC10195816.1.xml', primary_receipt=acquisition/'result.json',
        primary_metadata=acquisition/'metadata.json', primary_reading=primary/'coordinator-reading.json')
    files = list(paths.values()) + [Path(__file__), Path('scripts/run_canonical_immune_writer_quotes_20261115.py'), Path('scripts/experiment_error_receipt.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    return case, units, common, reader, files


def writer_prompt(common, notes):
    return common + '\nFALLIBLE SOURCE-ONLY EXPLANATIONS:\n' + json.dumps(notes, ensure_ascii=False) + (
        '\nSource explanations are fallible interpretations, never evidence or verified facts. '
        'Both original source units and their actual material scope govern. The old draft is navigation, '
        'not evidence. Preserve useful requested details and qualifiers; distinguish each published '
        'experiment from proposals. Answer the original user request with ONE complete useful Chinese '
        'report, actual numeric source citations and ordinary Markdown. No implementation labels, '
        'audit table, JSON or invented bibliography. Do not replace actual procedures with generic '
        'uncertainty. No outside facts.\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--preflight', type=Path)
    p.add_argument('--replay-attempt', type=Path)
    p.add_argument('--reader-cache', type=Path)
    p.add_argument('--tokenizer-file', type=Path)
    args = p.parse_args()
    assert not (args.execute and args.replay_attempt)
    args.out_dir.mkdir(exist_ok=False)
    case, units, common, reader, files = prepare()
    if args.execute:
        assert args.preflight and read(args.preflight/'completion.json')['status'] == 'preflight_only'
        assert all(sha(Path(k)) == h for k,h in read(args.preflight/'prestart-freeze.json').items())
        assert (args.preflight/'reader-prompt.txt').read_text() == reader
        assert (args.preflight/'common-writer-context.txt').read_text() == common
        files.extend(args.preflight/name for name in ['completion.json','prestart-freeze.json','plan.json'])
    if args.replay_attempt:
        files.extend(f for f in args.replay_attempt.glob('call-*') if f.is_file())
        files.append(args.replay_attempt/'calls.json')
    calibration = Path('evaluation/frontier-strategy-20261113/source-explanation-writer-pair-model-20261115-v1/attempt')
    if args.reader_cache:
        files.extend(args.reader_cache/name for name in ['calls.json','call-00-prompt.txt','call-00-response.txt'])
    if args.tokenizer_file:
        files.extend([args.tokenizer_file, calibration/'calls.json', calibration/'call-01-prompt.txt'])
    frozen = {str(f):sha(f) for f in files}
    write(args.out_dir/'prestart-freeze.json', frozen)
    for f in files:
        try:
            rel = f.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            continue  # Explicit tokenizer input outside repo remains hash-frozen.
        if str(rel).startswith(('scripts/','local_deep_research/')):
            target = args.out_dir/'code'/rel; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    write(args.out_dir/'source-units.json', units)
    (args.out_dir/'reader-prompt.txt').write_text(reader)
    (args.out_dir/'common-writer-context.txt').write_text(common)
    settings = {'llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':12000,'llm.max_retries':0,'llm.request_timeout':180}
    write(args.out_dir/'plan.json', dict(scope=__doc__, settings=settings, maximum_fresh_calls=2 if args.reader_cache else 3,
        original_query_sha256=case['query_sha256'], source_units=len(units), common_writer_chars=len(common),
        source_addition='New source11primary body in BOTH arms, not retroactive historical evidence.',
        source_explanations='Candidate only; strict reuse of original source-only Reader, extra historical reader compute disclosed.',
        strict_reader_cache=str(args.reader_cache) if args.reader_cache else None,
        duplicated_original_appendix_removed=True, actual_original_source_paragraphs_preserved=True,
        budget_policy='Frozen bundled LiteLLM DeepSeek tokenizer proxy, calibrated against actual same-alias historical Writer usage;10percent estimate margin plus8192token reserve. Not verified endpoint tokenizer/checkpoint.',
        writer_prompt_limit=480000, reader_prompt_limit=180000, original_prefix_preserved=True,
        native_fact_consistency_setting=True, full_native_pipeline_complete=False, save_time_citation_qc=False,
        known_task_not_heldout=True, new_independent_correction_credit=0))
    calls=[];model=None;failure=None
    def invoke(prompt, stage):
        nonlocal model
        assert len(calls)<3 and len(prompt) <= (180000 if stage=='source_explanations' else 480000)
        i=len(calls); pp=args.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt)
        row=dict(index=i,stage=stage,status='started',prompt_chars=len(prompt),prompt_sha256=sha(pp));calls.append(row)
        write(args.out_dir/'calls.json',calls)
        if args.replay_attempt:
            prior=read(args.replay_attempt/'calls.json')[i]
            rp=args.replay_attempt/f'call-{i:02d}-response.txt'
            assert prior['stage']==stage and prior['status']=='returned'
            assert prior['prompt_sha256']==sha(pp) and sha(rp)==prior['response_sha256']
            assert (args.replay_attempt/pp.name).read_bytes()==pp.read_bytes()
            raw=rp.read_text();metadata=prior['response_metadata'];row['origin']='strict_replay'
        elif args.reader_cache and stage=='source_explanations':
            prior=read(args.reader_cache/'calls.json')[0];rp=args.reader_cache/'call-00-response.txt'
            assert prior['stage']==stage and prior['status']=='returned' and prior['response_metadata']['finish_reason']=='stop'
            assert prior['prompt_sha256']==sha(pp) and sha(rp)==prior['response_sha256']
            assert (args.reader_cache/'call-00-prompt.txt').read_bytes()==pp.read_bytes()
            raw=rp.read_text();metadata=prior['response_metadata'];row['origin']='strict_reader_cache'
        elif args.execute:
            row['origin']='fresh_model';write(args.out_dir/'calls.json',calls)
            if model is None:
                from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                from local_deep_research.config.thread_settings import settings_context
                from local_deep_research.config.llm_config import get_llm
                defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'))
                effective=apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()})|settings|{'llm.provider':'openai_endpoint'}
                with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
            response=model.invoke(prompt);raw=str(response.content);metadata=response.response_metadata
        else:
            row['origin']='preflight_placeholder';metadata={}
            raw=json.dumps({'answers':[dict(source_id=sid,explanation='',evidence_units=[],unresolved_scope='preflight only') for sid in sorted({u['source_id'] for u in units})]}) if stage=='source_explanations' else 'Preflight only; not a report.'
        rp=args.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw)
        row.update(status='returned',response_sha256=sha(rp),response_metadata=metadata);write(args.out_dir/'calls.json',calls)
        if args.execute:assert metadata.get('finish_reason')=='stop'
        return raw
    try:
        notes=parse_explanations(invoke(reader,'source_explanations'),units)
        write(args.out_dir/'source-explanations.json',notes)
        prompts=[writer_prompt(common,[]),writer_prompt(common,notes)]
        for i,prompt in enumerate(prompts):
            assert len(prompt)<=480000
            (args.out_dir/f'writer-{i}-precall-prompt.txt').write_text(prompt)
        write(args.out_dir/'writer-precall-freeze.json', {f'writer-{i}-precall-prompt.txt':sha(args.out_dir/f'writer-{i}-precall-prompt.txt') for i in range(2)})
        if args.replay_attempt:
            budget=read(args.replay_attempt/'writer-token-budget.json')
            assert budget['prompt_sha256s']==[sha(args.out_dir/f'writer-{i}-precall-prompt.txt') for i in range(2)]
            assert budget['both_within_estimated_budget']
        else:
            assert args.tokenizer_file is not None, 'Explicit local tokenizer proxy required before Writer calls'
            from tokenizers import Tokenizer
            tokenizer=Tokenizer.from_file(str(args.tokenizer_file))
            oldcall=read(calibration/'calls.json')[1]
            assert sha(calibration/'call-01-prompt.txt')==oldcall['prompt_sha256']
            measured=oldcall['response_metadata']['token_usage']['prompt_tokens']
            old_proxy=len(tokenizer.encode((calibration/'call-01-prompt.txt').read_text()).ids)
            ratio=max(1.0,measured/old_proxy)
            counts=[len(tokenizer.encode(prompt).ids) for prompt in prompts]
            estimates=[math.ceil(n*ratio*1.10) for n in counts]
            budget=dict(context_limit=131072,output_tokens=12000,reserve_tokens=8192,
                tokenizer_sha256=sha(args.tokenizer_file),tokenizer_identity='Local LiteLLM bundled DeepSeek tokenizer proxy, endpoint checkpoint unverified',
                calibration_measured_tokens=measured,calibration_proxy_tokens=old_proxy,
                calibration_scale=ratio,estimate_margin=1.10,proxy_prompt_tokens=counts,
                conservative_estimated_prompt_tokens=estimates,
                prompt_sha256s=[sha(args.out_dir/f'writer-{i}-precall-prompt.txt') for i in range(2)],
                both_within_estimated_budget=all(n+12000+8192<=131072 for n in estimates))
            assert budget['both_within_estimated_budget'], 'Writer token estimate exceeds reserved context budget'
        write(args.out_dir/'writer-token-budget.json',budget)
        if args.preflight:
            assert budget==read(args.preflight/'writer-token-budget.json')
        for i,prompt in enumerate(prompts):
            assert sha(args.out_dir/f'writer-{i}-precall-prompt.txt') == read(args.out_dir/'writer-precall-freeze.json')[f'writer-{i}-precall-prompt.txt']
            report=invoke(prompt,'baseline_writer' if i==0 else 'explanation_writer');assert report.strip()
            (args.out_dir/('baseline-report.md' if i==0 else 'candidate-report.md')).write_text(report)
    except Exception as exc:
        failure=error_receipt(exc);write(args.out_dir/'failure.json',failure)
    completion=dict(status='unavailable' if failure else ('preflight_only' if not args.execute and not args.replay_attempt else 'completed_paired_writer_stage'), failure=failure,
        fresh_calls=sum(c.get('origin')=='fresh_model' for c in calls),logical_calls=len(calls),
        frozen_inputs_unchanged=all(sha(Path(k))==h for k,h in frozen.items()),
        full_native_pipeline_complete=False, independent_assessment_complete=False, new_independent_correction_credit=0)
    write(args.out_dir/'completion.json',completion);print(json.dumps(completion))
    if failure or not completion['frozen_inputs_unchanged']:raise SystemExit(2)


if __name__=='__main__':main()
