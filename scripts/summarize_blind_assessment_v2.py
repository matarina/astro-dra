#!/usr/bin/env python3
"""Join corrected blinded assessment v2 to hidden run metadata."""
from __future__ import annotations
import collections,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113'
def main():
 packets=json.loads((D/'judge-inputs.json').read_text()); by={p['result_id']:p for p in packets}; rows=[]
 for p in packets:
  f=D/f"{p['blind_id']}.json"; d=json.loads(f.read_text()); a=d.get('assessment',{}); scores=a.get('scores') if isinstance(a.get('scores'),dict) else a; score_shape='nested_scores' if isinstance(a.get('scores'),dict) else 'top_level'; claims=a.get('claim_assessments',[]); counts=collections.Counter(x.get('verdict') for x in claims); rows.append({'blind_id':p['blind_id'],'result_id':p['result_id'],'case_id':p['case_id'],'result_path':p['result_path'],'report_sha256':p['report_sha256'],'verdict_counts':dict(counts),'claim_count':len(claims),'claim_protocol_deviation':len(claims)>8,'score_shape':score_shape,'citation_entailment':scores.get('citation_entailment'),'qualifier_retention':scores.get('qualifier_retention'),'important_content_coverage':scores.get('important_content_coverage'),'scope_compliance':scores.get('scope_compliance'),'usefulness':scores.get('usefulness'),'omissions':a.get('omissions',[]),'unresolved':a.get('unresolved',[]),'parse_error':d.get('parse_error',False)})
 key=json.loads((D/'answer-key-private.json').read_text()); cal=json.loads((D/'calibration-assessment.json').read_text()).get('assessment',{}); predicted={str(x.get('control_id')):x.get('verdict') for x in cal.get('controls',[])} if isinstance(cal,dict) else {}; known={str(x['control_id']):x['verdict'] for x in key}; matches=sum(predicted.get(k)==v for k,v in known.items())
 result={'schema_version':'scholar_blind_assessment_v2_summary.v1','status':'valid_blinded_assessment_complete','reports':len(rows),'rows':rows,'calibration':{'known_labels_private':known,'predicted':predicted,'matches':matches,'n':len(known)},'limitations':['Same model/provider family as generation; not independent medical adjudication.','Case/question and cited source content were visible; arm settings and verdict labels were hidden.','Scores are provisional and source-bound; no corpus-wide recall or prevalence inference.','The identity correction changes metadata receipts only; old generation outputs remain historically labelled.']}
 result['calibration']['interpretation']='Observed label agreement only; not accuracy against matched evidence.'
 result['calibration']['evidence_scope_mismatch']=[{'control_id':'cal-02','original_claim_id':68,'gold_evidence_scope':'abstract_only','judge_evidence_scope':'full_article'},{'control_id':'cal-03','original_claim_id':41,'gold_evidence_scope':'abstract_only','judge_evidence_scope':'full_article'}]
 result['limitations'].append('Calibration controls 68/41 received full articles whereas their original gold labels were abstract-scoped; agreement cannot establish evaluator reliability.')
 (D/'summary-private.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'reports':len(rows),'calibration_matches':matches,'calibration_n':len(known)},ensure_ascii=False))
if __name__=='__main__':main()
