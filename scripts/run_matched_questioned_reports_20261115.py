"""Isolated complete-report pair; matched material and native budgets, no deployment.

Candidate questions are draft-informed hypotheses, facts are fallible readings.
A saved-response replay validates engineering only, never scientific accuracy.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from research_verify import evidence_flow
from research_verify.generation import format_source_documents
from research_verify.evidence_flow import cited_indices
from research_verify.source_questions import inventory, question_prompt, parse_questions
from research_verify.question_routing import route_questions
from research_verify.questioned_fact_document import answer_prompt, parse_answers, instructions, render
from scripts.run_complete_draft_pair_20261115 import FixedSources
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-manifest', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--replay-attempt', type=Path)
    a = p.parse_args()
    assert not (a.execute and a.replay_attempt)
    a.out_dir.mkdir(exist_ok=False)
    cases = _manifest_cases(a.case_manifest)
    assert len(cases) == 1
    case = cases[0]
    original = case['draft'].read_text()
    sources = json.loads(case['source'].read_text())
    assert original.strip() and sources
    files = [a.case_manifest, case['draft'], case['source'], Path(__file__).resolve().relative_to(Path.cwd()),
             Path('scripts/run_complete_draft_pair_20261115.py'),
             Path('scripts/prepare_source_detail_material_20261114.py'),
             Path('scripts/run_native_original_report_pair_20261114.py'),
             Path('scripts/run_hallucination_next_phase_experiment_20261113.py'),
             Path('scripts/experiment_error_receipt.py'),
             Path('local_deep_research/overlay/base_citation_handler.py'),
             *Path('local_deep_research/research_verify').glob('*.py')]
    frozen = {str(f): sha(f) for f in files}
    write(a.out_dir/'prestart-freeze.json', frozen)
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            dest = a.out_dir/'code'/f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
    prior_calls = json.loads((a.replay_attempt/'calls.json').read_text()) if a.replay_attempt else None
    prior_plan = json.loads((a.replay_attempt/'plan.json').read_text()) if a.replay_attempt else None
    clock = datetime.fromisoformat(prior_plan['fixed_writer_clock']) if prior_plan else datetime.now(timezone.utc)
    class FixedClock:
        @staticmethod
        def now(tz=None):
            return clock if tz is not None else clock.replace(tzinfo=None)
    evidence_flow.datetime = FixedClock
    # Isolated, declared cap override for BOTH arms; never a production edit.
    evidence_flow.SOURCE_CONTEXT_CHARS = 300000
    settings = {'general.enable_fact_checking': True, 'verify.enable_citation_qc': False,
                'citation.enable_source_reading': True, 'citation.enable_source_reading_roles': False,
                'citation.fresh_evidence_synthesis': False, 'citation.source_context_chars': 300000,
                'citation.max_review_calls': 16, 'citation.fetch_cited_source_bodies_before_writing': False,
                'citation.claim_directed_source_context': False, 'citation.identity_attribute_review': False,
                'citation.semantic_passage_ranking': False, 'llm.model': 'deepseek-v4-flash',
                'llm.temperature': 0, 'llm.max_tokens': 8000, 'llm.max_retries': 0}
    plan = dict(case_id=case['case_id'], query=case['query'], query_sha256=case['query_sha256'],
                source_pack_sha256=sha(case['source']), original_report_sha256=sha(case['draft']),
                original_report_chars=len(original), source_count=len(sources), settings=settings,
                fixed_writer_clock=clock.isoformat(), maximum_baseline_calls=18,
                isolated_source_cap_override=300000,
                maximum_candidate_fresh_calls=24, maximum_source_answer_batches=6,
                maximum_native_calls_per_arm=16, maximum_prompt_chars=500000,
                scope='Known original task, complete matched report comparison; same materials, clock, inherited draft, native budgets and exact shared reader response. Candidate adds draft-informed questions, ID alias routing, source answer calls and fact/identity rendering. Extra compute, not cost parity. 300000 source context and 16 native calls are experimental, not production settings or Xenium compute parity.',
                scientific_status='not_independently_assessed', newly_credited_corrections=0)
    if prior_plan:
        assert plan == prior_plan
    write(a.out_dir/'plan.json', plan)
    material = format_source_documents(native_documents(sources), case['query'], max_chars=300000, required_ids=cited_indices(original), reading_scope=[])
    (a.out_dir/'source-material.txt').write_text(str(material))
    write(a.out_dir/'source-views.json', material.views)
    claims = inventory(original)
    write(a.out_dir/'inventory.json', claims)
    calls, results, shared, writer_prompts = [], [], {}, {}
    model = None

    def persist():
        write(a.out_dir/'calls.json', calls)

    def invoke(arm, stage, prompt):
        nonlocal model
        i = len(calls)
        assert len(prompt) <= plan['maximum_prompt_chars']
        if arm == 'baseline':
            assert sum(c['arm'] == arm for c in calls) < 18
        else:
            assert sum(c['arm'] == arm and c['stage'] != 'source_reading' for c in calls) < 24
        pp = a.out_dir/f'call-{i:02d}-prompt.txt'
        pp.write_text(prompt)
        row = dict(index=i, arm=arm, stage=stage, prompt_sha256=sha(pp), prompt_chars=len(prompt), status='started')
        calls.append(row)
        persist()
        try:
            if prior_calls is not None:
                old = prior_calls[i]
                op = a.replay_attempt/f'call-{i:02d}-prompt.txt'
                rp = a.replay_attempt/f'call-{i:02d}-response.txt'
                assert (arm, stage, prompt) == (old['arm'], old['stage'], op.read_text())
                assert sha(op) == old['prompt_sha256'] and sha(rp) == old['response_sha256']
                raw, metadata = rp.read_text(), old['response_metadata']
                row.update(origin='saved_response_replay', replay_origin=old['origin'])
                if arm == 'candidate' and stage == 'source_reading':
                    assert shared[prompt] == (raw, metadata)
            elif arm == 'candidate' and stage == 'source_reading':
                raw, metadata = shared[prompt]
                row['origin'] = 'strict_shared_source_reading'
            elif a.execute:
                row['origin'] = 'fresh_model'
                persist()
                if model is None:
                    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
                    from local_deep_research.config.thread_settings import settings_context
                    from local_deep_research.config.llm_config import get_llm
                    defaults = json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
                    effective = apply_environment_overrides_to_snapshot({k:v.get('value') for k,v in defaults.items()}) | settings | {'llm.provider':'openai_endpoint','llm.request_timeout':180}
                    with settings_context(type('Settings', (), {'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):
                        model = get_llm(settings_snapshot=effective)
                response = model.invoke(prompt)
                raw, metadata = str(getattr(response, 'content', response)), getattr(response, 'response_metadata', {})
            else:
                row['origin'] = 'preflight_placeholder'
                raw = (original if arm == 'baseline' else json.dumps({'nodes':[{'kind':'text','text':original}]}, ensure_ascii=False)) if stage == 'writer' else {'source_reading':'{"readings":[]}', 'source_questions':'{"questions":[]}', 'source_answers':'{"sources":[]}'}.get(stage, '{"issues":[]}')
                metadata = {}
            if stage == 'source_reading':
                shared[prompt] = raw, metadata
            rp = a.out_dir/f'call-{i:02d}-response.txt'
            rp.write_text(raw)
            row.update(status='returned', response_sha256=sha(rp), response_metadata=metadata)
            return raw
        except Exception as exc:
            row.update(status='unavailable', failure=error_receipt(exc))
            raise
        finally:
            persist()

    for arm in ['baseline', 'candidate']:
        folder = a.out_dir/arm
        folder.mkdir()
        trace, fetch = Trace(folder/'trace.jsonl'), FixedSources()
        arm_sources, registry = copy.deepcopy(sources), {}
        class Handler:
            stream_callback = None
            settings_snapshot = settings
            evidence_fetcher = fetch
            def get_setting(self, k, d=None): return self.settings_snapshot.get(k,d)
            def is_fact_checking_enabled(self): return True
            def _get_output_instruction_prefix(self): return '请用中文回答原始用户问题。\n'
            def _create_documents(self, sources, nr_of_links=0): return native_documents(sources)
            def _no_sources_response(self, q): raise ValueError('No actual source material')
            def _invoke_text(self, prompt, trace=None, stage='model'):
                if stage == 'writer':
                    writer_prompts[arm] = prompt
                    assert str(material) in prompt and original in prompt
                    if arm == 'candidate':
                        assert prompt == writer_prompts['baseline']
                        raw = invoke(arm, 'source_questions', question_prompt(case['query'], claims))
                        questions = parse_questions(raw, claims)
                        write(folder/'questions.json', questions)
                        routes = route_questions(questions['questions'], sources)
                        write(folder/'source-question-routes.json', routes)
                        byid = {str(s['index']):s for s in sources}
                        batches, batch, used = [], [], 0
                        for sid, view in material.views.items():
                            record = dict(source_id=int(sid), title=byid[str(sid)].get('title'), metadata=view['metadata'], text=view['text'], scope=view['scope'], evidence_questions=[q for q in routes if q['reader_source_id']==str(sid)])
                            size = len(json.dumps(record, ensure_ascii=False))
                            assert size < 100000
                            if batch and (used+size > 100000 or len(batch)>=12):
                                batches.append(batch)
                                batch, used = [], 0
                            batch.append(record)
                            used += size
                        if batch: batches.append(batch)
                        assert len(batches) <= 6
                        write(folder/'source-answer-batches.json', batches)
                        for batch_index, batch in enumerate(batches):
                            aux = answer_prompt(case['query'], batch)
                            assert len(aux) < 110000
                            parsed = parse_answers(invoke(arm, 'source_answers', aux), batch)
                            assert not set(registry) & set(parsed['registry'])
                            registry.update(parsed['registry'])
                            write(folder/f'source-answers-{batch_index:02d}.json', parsed)
                        write(folder/'fact-registry.json', registry)
                        prompt += instructions(arm_sources, registry)
                raw = invoke(arm, stage, prompt)
                if arm == 'candidate' and stage == 'writer':
                    rendered, receipts = render(raw, arm_sources, registry)
                    (folder/'writer-rendered.txt').write_text(rendered)
                    write(folder/'fact-rendering.json', receipts)
                    return rendered
                return raw
        try:
            result = evidence_flow.synthesize(Handler(), case['query'], arm_sources, original, trace)
            (folder/'report.txt').write_text(result['content'])
            row = dict(arm=arm, status='completed', report_chars=len(result['content']), report_sha256=sha(folder/'report.txt'), native_review=result['evidence_review'], sources=arm_sources, supplement_requests=fetch.events)
        except Exception as exc:
            row = dict(arm=arm, status='unavailable', failure=error_receipt(exc))
        write(folder/'result.json', row)
        results.append({k:v for k,v in row.items() if k!='sources'})
        if row['status'] != 'completed': break
    replay_exact = None
    if prior_calls is not None:
        assert len(calls) == len(prior_calls)
        for row in results:
            old = json.loads((a.replay_attempt/row['arm']/'result.json').read_text())
            assert row == {k:v for k,v in old.items() if k!='sources'}
            if row['status'] == 'completed':
                assert (a.out_dir/row['arm']/'report.txt').read_bytes() == (a.replay_attempt/row['arm']/'report.txt').read_bytes()
        for f in ['questions.json','source-question-routes.json','source-answer-batches.json','fact-registry.json','fact-rendering.json']:
            assert json.loads((a.out_dir/'candidate'/f).read_text()) == json.loads((a.replay_attempt/'candidate'/f).read_text())
        replay_exact = True
    completion = dict(arms=results, logical_calls=len(calls), fresh_model_requests=sum(c.get('origin')=='fresh_model' for c in calls), strict_shared_calls=sum(c.get('origin')=='strict_shared_source_reading' for c in calls), replay_exact=replay_exact, frozen_inputs_unchanged=all(sha(Path(k))==v for k,v in frozen.items()), retrieval_network_reads=0, new_independent_correction_credit=0, scientific_status='not_independently_assessed')
    write(a.out_dir/'completion.json', completion)
    print(json.dumps({k:v for k,v in completion.items() if k!='arms'}))
    if any(r['status'] != 'completed' for r in results): raise SystemExit(2)


if __name__ == '__main__':
    main()
