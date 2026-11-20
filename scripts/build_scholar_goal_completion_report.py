#!/usr/bin/env python3
"""Assemble the empirical scholar-goal completion report."""
from __future__ import annotations
import collections, hashlib, json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/scholar-strategy-20261112/scholar-goal-completion-report-20261113.json'

def read_results(root: Path):
 rows=[]
 for p in sorted(root.glob('*/**/result.json')):
  d=json.loads(p.read_text()); row={**d,'result_path':str(p.relative_to(ROOT))}
  calls_path=p.parent/'calls.json'; usage={'calls':0,'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
  if calls_path.exists():
   try:
    for event in json.loads(calls_path.read_text()):
     usage['calls']+=1; tu=(event.get('metadata') or {}).get('token_usage') or {}
     for key in ('prompt_tokens','completion_tokens','total_tokens'): usage[key]+=int(tu.get(key) or 0)
   except Exception: usage['parse_error']=True
  row['usage_totals']=usage; rows.append(row)
 return rows

def summarize_arms(rows):
 arm_metrics={}
 for arm in sorted(set(x.get('arm') for x in rows)):
  rs=[x for x in rows if x.get('arm')==arm]
  arm_metrics[arm]={"runs":len(rs),"completed":sum(x.get('status')=='completed' for x in rs),"references":[x.get('references') for x in rs],"report_chars":[x.get('report_chars') for x in rs],"elapsed_s":[x.get('elapsed_s') for x in rs],"model_calls":[x.get('model_calls') for x in rs],"draft_chars":[x.get('draft_chars') for x in rs],"usage_totals":[x.get('usage_totals') for x in rs]}
 return arm_metrics

def main():
 corrected=read_results(ROOT/'evaluation/scholar-controlled-pilot-corrected-20261112/results')
 new=read_results(ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112/results')
 valid_corrected=[x for x in corrected if x.get('status')=='completed']
 valid_new=[x for x in new if x.get('status')=='completed']
 old_mislabel=[x for x in corrected if x.get('case_id') in {'new-certolizumab','new-xlinked-epilepsy'}]
 historical=[x for x in valid_corrected if x.get('case_id','').startswith('historical-')]
 assessment_v1_invalid=json.loads((ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-20261112/summary.json').read_text())
 assessment_v2=json.loads((ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113/summary.json').read_text())
 assessment_v2['status']='canonical_valid_v2_assessment'
 historical_arm_metrics=summarize_arms(historical)
 new_arm_metrics=summarize_arms(valid_new)
 result={
  "schema_version":"scholar_goal_completion_report.v1",
  "status":"bounded_experiments_and_provisional_assessment_complete",
  "historical_controlled_runs":{"completed":len(historical),"cases":sorted(set(x.get('case_id') for x in historical)),"arms":historical_arm_metrics},
  "new_validation":{"completed":len(valid_new),"cases":sorted(set(x.get('case_id') for x in valid_new)),"arms":new_arm_metrics,"source_manifest":"evaluation/scholar-controlled-pilot-corrected-v2-20261112/manifest.json","novelty_receipt":"/data1/maxw/.local/state/dra-hourly-monitor/20261113-0109-corrected-identity-overlap.json","corrected_identity_overlap_receipt":"/data1/maxw/.local/state/dra-hourly-monitor/20261113-0109-corrected-identity-overlap.json","offline_doi_parser_receipt":"/data1/maxw/.local/state/dra-hourly-monitor/20261113-0109-offline-doi-check.json","novelty_scope":"ten-family pre-run exclusion inventory plus frozen November 11 source-pack JSON files; not global project or semantic overlap"},
  "assessment":assessment_v2,
  "assessment_v1_invalid":{"status":"superseded_invalid_for_arm_leakage_missing_report_and_inconsistent_calibration","receipt":"evaluation/scholar-strategy-20261112/pilot-assessment-20261112/summary.json","reports":assessment_v1_invalid.get('counts',{}).get('reports'),"known_protocol_deviations":["One old retry used an aggregate-only score schema; it is not combined with v2 scores."]},
  "assessment_v2":assessment_v2,
  "assessment_provenance":"evaluation/scholar-strategy-20261112/assessment-provenance-v2-20261113.json",
  "excluded_or_failed":{"old_mislabelled_new_task_results":len(old_mislabel),"old_mislabel_correction":"evaluation/scholar-controlled-pilot-corrected-20261112/label-correction-20261112.json","interrupted_runs":[x for x in corrected if x.get('status')!='completed']},
  "decision":{"recommendation":"defer production adoption","reasoning":["Candidate A ran with matched nonempty drafts on three historical tasks and on two genuinely new tasks, but provisional assessments show no credible comparative factual/usefulness advantage.","Candidate B ran with draft removed on the same historical source packs and on two new tasks; it changed outputs, but draft removal is confounded by changed reading-note context and is not a causal anchoring result.","The v2 same-model assessment agreed with 1/3 supplied labels. Two controls received full articles whereas their original gold labels were abstract-scoped; this is not matched-evidence accuracy and cannot establish evaluator reliability or comparative benefit/harm.","No population-level hallucination-rate claim is justified from this bounded pilot."]},
  "production_scope":{"model_unchanged":"deepseek-v4-flash","source_pool_unchanged":"PubMed/SearXNG/Europe PMC","native_fact_consistency":True,"save_time_citation_audit":False,"deployment_or_restart":False},
  "limitations":["Historical supplemented IF arm was interrupted after a persisted partial trace; no completed paired supplemented result exists for that case.","Assessment samples cited-source material and does not prove recall of uncited source evidence.","Useful-information scores and factual verdicts are provisional same-model judgments.","Calibration controls cal-02/claim 68 and cal-03/claim 41 use broader evidence than their original abstract-scoped gold labels; 1/3 is observed label agreement, not matched-evidence accuracy.","V2 IF/candidate B assessment judge-a4cbd413e674262b sampled 10 claims despite an eight-claim prompt limit; all ten and the deviation flag are retained.","New validation comprises two single-abstract tasks with empty inherited drafts; it does not establish draft-removal benefit or general multi-paper report performance.","Old certolizumab/DEE runs are preserved as regressions and excluded from new-task validation."]
 }
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'historical_completed':len(historical),'new_completed':len(valid_new),'assessment_reports':assessment_v2['reports'],'decision':result['decision']['recommendation']},ensure_ascii=False))
if __name__=='__main__':main()
