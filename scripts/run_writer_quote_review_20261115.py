"""Bounded native-check-stage experiment; complete reports are never rewritten."""
import argparse
import hashlib
import json
from pathlib import Path

from research_verify.generation import SourceMaterial
from research_verify.writer_quote_evidence import carry_writer_quotes
from research_verify.evidence_flow import parse_review
from scripts.audit_material_exposure_20261115 import extracted_review_material
from scripts.experiment_error_receipt import error_receipt


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def write(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, default=str)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--replay-attempt', type=Path)
    a = p.parse_args()
    assert not(a.execute and a.replay_attempt)
    a.out_dir.mkdir(exist_ok=False)
    root = Path('evaluation/frontier-strategy-20261113')
    immune = root/'section-native-model-20261115-v1/attempt'
    xeno = root/'questioned-fact-document-model-20261115-v1/attempt'
    cases = [dict(name='immune', attempt=immune, folder=immune/'section', rendering='rendering.json',
                  registry=root/'immune-questioned-fact-model-20261115-v1/attempt/candidate/fact-registry.json'),
             dict(name='xenium', attempt=xeno, folder=xeno/'fact_document', rendering='fact-rendering.json',
                  registry=xeno/'fact_document/fact-registry.json')]
    inputs, pairs, controls = [], [], []
    for case in cases:
        folder, attempt = case['folder'], case['attempt']
        files = [folder/'trace.jsonl', folder/'report.txt', folder/case['rendering'],
                 case['registry'], attempt/'plan.json', attempt/'calls.json']
        inputs += files
        events = [json.loads(line) for line in files[0].read_text().splitlines()]
        source_views = next(e['data']['sources'] for e in events if e['stage']=='source_material_views')
        writer_text = next(e['data']['text'] for e in events if e['stage']=='writer_sources')
        writer = SourceMaterial(writer_text, {int(v['index']):v for v in source_views})
        report = files[1].read_text()
        rendering = json.loads(files[2].read_text())
        registry = json.loads(case['registry'].read_text())
        calls = json.loads((attempt/'calls.json').read_text())
        for e in events:
            if e['stage']!='native_check_request' or e['data']['round']!=1:
                continue
            data = e['data']
            prompt = data['prompt']
            claims = json.loads(prompt.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
            old = extracted_review_material(prompt, data['source_ids'])
            material, receipt = carry_writer_quotes(writer, old, report, registry, rendering, claims)
            assert not receipt['rejected_bindings']
            matches = [c for c in calls if c['prompt_sha256']==digest(prompt)]
            assert len(matches)==1
            call = matches[0]
            op, response = attempt/f"call-{call['index']:02d}-prompt.txt", attempt/f"call-{call['index']:02d}-response.txt"
            assert op.read_text()==prompt and sha(op)==call['prompt_sha256'] and sha(response)==call['response_sha256']
            inputs += [op, response]
            key = case['name']+'-group-'+str(data['review_group'])
            if not receipt['additions']:
                assert str(material)==str(old)
                controls.append(dict(key=key, baseline_prompt_sha256=digest(prompt),
                                     exact_noop=True, quote_bindings=len(receipt['quote_bindings'])))
                continue
            prefix, remainder = prompt.split('SUPPLIED SOURCES:\n',1)
            serialized, suffix = remainder.split('\n\nSTRUCTURAL REPORT SPANS',1)
            assert serialized==str(old)
            newprompt = prefix+'SUPPLIED SOURCES:\n'+str(material)+'\n\nSTRUCTURAL REPORT SPANS'+suffix
            assert len(prompt)<=60000 and len(newprompt)<=60000
            pairs.append(dict(key=key, prompt=newprompt, claims=claims, receipt=receipt,
                              baseline_path=str(response), baseline_metadata=call['response_metadata'],
                              baseline_prompt_sha256=digest(prompt), baseline_response_sha256=sha(response),
                              settings=json.loads((attempt/'plan.json').read_text())['settings']))
    assert 0 < len(pairs) <= 5
    files = [Path(__file__).resolve().relative_to(Path.cwd()), Path('scripts/audit_material_exposure_20261115.py'),
             Path('scripts/experiment_error_receipt.py'), *inputs,
             Path('local_deep_research/tests/test_writer_quote_evidence.py'),
             *Path('local_deep_research/research_verify').glob('*.py')]
    if a.replay_attempt:
        files += [a.replay_attempt/'plan.json', a.replay_attempt/'completion.json']
        files += [a.replay_attempt/pair['key']/name for pair in pairs
                  for name in ['prompt.txt','response.txt','result.json','quotation-receipt.json']]
    frozen = {str(f):sha(f) for f in files}
    write(a.out_dir/'prestart-freeze.json', frozen)
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            dest = a.out_dir/'code'/f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    plan = dict(scope='Native-check-stage diagnostic on two KNOWN complete reports. '
                     'All first-round groups where generated selected facts lost exact bound quotations. '
                     'Only same-source original windows added inside source blocks; all original prompt/source '
                     'bytes retained. No report generation/repair, independent adjudication or quality score.',
                maximum_fresh_calls=len(pairs), context_chars_each_side=400, native_prompt_budget=60000,
                pairs=[dict(key=x['key'], baseline_prompt_sha256=x['baseline_prompt_sha256'],
                            baseline_response_sha256=x['baseline_response_sha256'],
                            prompt_sha256=digest(x['prompt']), prompt_chars=len(x['prompt']),
                            settings=x['settings'])for x in pairs], controls=controls,
                new_independent_correction_credit=0)
    write(a.out_dir/'plan.json',plan)
    results=[]
    for pair in pairs:
        folder=a.out_dir/pair['key'];folder.mkdir()
        (folder/'prompt.txt').write_text(pair['prompt'])
        (folder/'baseline-response.txt').write_bytes(Path(pair['baseline_path']).read_bytes())
        write(folder/'quotation-receipt.json', pair['receipt'])
        row=dict(key=pair['key'], prompt_sha256=sha(folder/'prompt.txt'))
        try:
            if a.replay_attempt:
                prior=a.replay_attempt/pair['key'];old=json.loads((prior/'result.json').read_text())
                assert (prior/'prompt.txt').read_text()==pair['prompt'] and old['prompt_sha256']==row['prompt_sha256']
                assert sha(prior/'response.txt')==old['response_sha256']
                raw=(prior/'response.txt').read_text();metadata=old['response_metadata'];origin='saved_response_replay'
            elif a.execute:
                from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                from local_deep_research.config.thread_settings import settings_context
                from local_deep_research.config.llm_config import get_llm
                defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
                settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|pair['settings']|{'llm.provider':'openai_endpoint','llm.request_timeout':180,'llm.max_retries':0}
                with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:settings.get(k,d))})()):model=get_llm(settings_snapshot=settings)
                response=model.invoke(pair['prompt']);raw=str(response.content);metadata=response.response_metadata;origin='fresh_model'
            else:
                raw=Path(pair['baseline_path']).read_text();metadata={};origin='preflight_saved_baseline_placeholder'
            (folder/'response.txt').write_text(raw)
            row.update(response_sha256=sha(folder/'response.txt'), response_metadata=metadata, origin=origin)
            write(folder/'result.json',row)
            claims={c['claim_id']:c for c in pair['claims']}
            issues, checked=parse_review(raw,claims,include_checked=True)
            row.update(status='parsed', native_issues=issues, native_checked=checked,
                       checked_claim_ids=sorted({c['claim_id'] for c in checked}))
            if a.replay_attempt:
                if old['status']=='parsed':
                    assert row['native_issues']==old['native_issues'] and row['checked_claim_ids']==old['checked_claim_ids']
                else:
                    row['prior_parse_failure']=old['failure']
        except Exception as exc:
            row.update(status='unavailable', failure=error_receipt(exc))
        write(folder/'result.json',row);results.append(row)
    completion=dict(results=results, frozen_inputs_unchanged=all(sha(Path(f))==h for f,h in frozen.items()),
                    fresh_calls=sum(r.get('origin')=='fresh_model'for r in results),
                    replay_exact=bool(a.replay_attempt) and all(r['status']=='parsed'for r in results),
                    report_rewrites=0, new_independent_correction_credit=0)
    write(a.out_dir/'completion.json',completion)
    print(json.dumps({k:v for k,v in completion.items()if k!='results'}))
    if any(r['status']=='unavailable'for r in results):
        raise SystemExit(2)


if __name__=='__main__':
    main()
