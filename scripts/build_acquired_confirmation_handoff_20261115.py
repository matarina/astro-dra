"""Coordinator package for a default-off confirmation evidence-context candidate."""
import json,hashlib,shutil,difflib
from pathlib import Path
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 out=R/'acquired-confirmation-coordinator-handoff-20261115-v2';out.mkdir(exist_ok=False)
 model=R/'acquired-confirmation-model-20261115-v1/attempt';replay=R/'acquired-confirmation-native-replay-20261115-v1';prior=R/'source-view-native-coordinator-handoff-20261115-v1/assessment-input'
 assessment=out/'assessment-input';assessment.mkdir();mapping={}
 for label,arm in [('A','complete_acquired_context'),('B','selected_context')]:
  path=replay/arm/'native-report.md';shutil.copyfile(path,assessment/f'document-{label}.md');mapping[label]=dict(arm=arm,sha256=sha(path),origin='Composed exact native replay using historical checks plus actual fresh confirmation for A; no full fresh Writer/native experiment')
 original=model/'job-00/original-report.md';shutil.copyfile(original,assessment/'document-C.md');mapping['C']=dict(arm='shared_original_writer_report',sha256=sha(original))
 for name in ['original-question.txt','sources.json','generation-source-material.json','primary-index.json',*[p.name for p in prior.glob('primary-source-*.xml')]]:shutil.copyfile(prior/name,assessment/name)
 write(assessment/'status.json',dict(status='UNASSESSED',scope='Three complete reports and original evidence; model transport and coordinator outcome are not an independent original-source correction/retention/new-error assessment. Acquired text is distinct from complete published paper. No image/supplement inspection implied.'))
 write(out/'document-mapping.json',mapping)
 calibration=out/'calibration-only-not-feedback';calibration.mkdir()
 for i in [2,3]:
  folder=calibration/f'job-{i:02d}';shutil.copytree(model/f'job-{i:02d}',folder)
 write(calibration/'status.json',dict(scope='Generated sign inversion of an existing report bullet, source-matched native calibration only. Never add to feedback denominator or independent corrected count. Both arms accept the original-source-supported sign correction.'))
 results=[]
 for i in range(4):
  folder=model/f'job-{i:02d}';d=read(folder/'result.json');results.append(dict(case=d['case'],arm=d['arm'],native_applied=len(d['applied']),native_unresolved=len(d['unresolved']),report_changed=d['report_changed'],prompt_sha256=sha(folder/'prompt.txt'),response_sha256=sha(folder/'response.txt')))
 for arm in ['selected_context','complete_acquired_context']:
  src=replay/arm/'native-report.md';(out/f'{arm}-complete-report-diff.patch').write_text(''.join(difflib.unified_diff(original.read_text().splitlines(True),src.read_text().splitlines(True))))
 write(out/'decision.json',dict(scope=__doc__,decision='Retain default-off engineering candidate; DEFER production/semantic adoption and majority/generalization claims',
  four_fresh_confirmation_results=results,full_native_composed_replay=dict(selected_applied=1,selected_unresolved=4,complete_applied=0,complete_unresolved=5,fresh_calls=0,original_report_retained_exactly_in_candidate=True),
  known_source_evidence_chain=str(R/'source-view-native-coordinator-handoff-20261115-v1/source9-repair-evidence-chain.json'),
  actual_delta='Only optional native confirmation evidence exposure. All explicitly referenced acquired source texts are shared once in a source registry; candidate references point to that registry. All complete texts must fit actual final prompt budget atomically; missing/ambiguous IDs, quote mismatch or oversized prompt returns exact original prompt with an explicit trace limit. Existing eligibility and semantic confirmation decide revisions; no new science rule, automatic content edit, hard publication gate or new default.',
  limitations=['One known source and one generated calibration; no generalization or original-feedback correction credit.',
   'Complete source exposure and shared context serialization jointly differ; this pair does not isolate their effects.',
   'Budget fallback retains the old selected-context path and therefore its known semantic risk; it is not a safe/verified result.',
   'No proposal means this helper is not invoked: requested-information omissions without emitted claims remain unaddressed.',
   'No fresh full Writer/native experiment or independent source/retention/new-error adjudication. Existing full report errors and omissions remain.',
   'Acquired-text completeness does not imply published-paper completeness or correct reading; model supported/decision labels remain fallible.'],
  next_work='Inspect other original tasks for actual harmful-repair or missed-requested-information traces; test context-fit and source/analysis scope before consuming reserved controls. For oversized evidence or absent claims, investigate bounded source-grounded answering of original requested fields, retaining acquired source sections/branches and unknowns. Do not expand a positive one-source confirmation into production or a majority score.',
  independent_correction_credit=0))
 for path in [Path(__file__),Path('local_deep_research/research_verify/confirmation_context.py'),Path('local_deep_research/research_verify/evidence_flow.py'),Path('local_deep_research/tests/test_confirmation_context.py'),Path('scripts/run_acquired_confirmation_pair_20261115.py'),Path('scripts/replay_acquired_confirmation_native_20261115.py'),Path('scripts/audit_acquired_confirmation_pair_20261115.py')]:
  dest=out/'code'/path.resolve().relative_to(Path.cwd());dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
 print(json.dumps(dict(handoff=str(out),neutral_complete_documents=3,independent_correction_credit=0)))
if __name__=='__main__':main()
