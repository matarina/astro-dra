#!/usr/bin/env python3
"""Join blinded provisional assessments to arm metadata after assessment."""
from __future__ import annotations
import collections, glob, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ASSESS=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-20261112'
RESULT_ROOTS=[ROOT/'evaluation/scholar-controlled-pilot-corrected-20261112/results',ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112/results']
OUT=ASSESS/'summary.json'

def metadata_ordered():
 out=[]
 for root in RESULT_ROOTS:
  for path in root.glob('*/**/result.json'):
   d=json.loads(path.read_text())
   if d.get('status')=='completed' and d.get('body'):
    import hashlib
    out.append({"case_id":d.get('case_id'),"arm":d.get('arm'),"status":d.get('status'),"references":d.get('references'),"report_chars":d.get('report_chars'),"elapsed_s":d.get('elapsed_s'),"model_calls":d.get('model_calls'),"draft_chars":d.get('draft_chars'),"source_sha256":d.get('source_sha256'),"report_sha256":hashlib.sha256(d['body'].encode()).hexdigest(),"result_path":str(path.relative_to(ROOT))})
 return out

def assessment_for(bid):
 candidates=[ASSESS/(bid+'-minimal.json'),ASSESS/(bid+'-retry.json'),ASSESS/(bid+'.json')]
 for path in candidates:
  if path.exists():
   d=json.loads(path.read_text())
   if not d.get('parse_error') and isinstance(d.get('assessment'),dict) and 'claim_assessments' in d['assessment'] or path.name.endswith('minimal.json'):
    return d
 return None

def main():
 meta=metadata_ordered(); packets=json.loads((ASSESS/'packets.json').read_text()); rows=[]
 by_hash=collections.defaultdict(list)
 for item in meta: by_hash[item['report_sha256']].append(item)
 for packet in packets:
  a=assessment_for(packet['blind_id']); queue=by_hash.get(packet['report_sha256'],[]); info=queue.pop(0) if queue else {}
  if not a:
   rows.append({"blind_id":packet['blind_id'],**info,"assessment_status":"unresolved_parse_failure"}); continue
  assessment=a['assessment']; counts=collections.Counter(x.get('verdict') for x in assessment.get('claim_assessments',[]))
  if not counts and any(k in assessment for k in ('supported','partially_supported','unsupported','contradicted','unverifiable')):
   counts=collections.Counter({k:assessment.get(k,0) for k in ('supported','partially_supported','unsupported','contradicted','unverifiable') if assessment.get(k,0)})
  rows.append({"blind_id":packet['blind_id'],**info,"assessment_status":"provisional_model_assessment","verdict_counts":dict(counts),"citation_entailment":assessment.get('citation_entailment'),"qualifier_retention":assessment.get('qualifier_retention'),"important_content_coverage":assessment.get('important_content_coverage'),"scope_compliance":assessment.get('scope_compliance'),"usefulness":assessment.get('usefulness'),"omissions":assessment.get('omissions',[]),"unresolved":assessment.get('unresolved',[]),"assessment_retry":a.get('retry')})
 calibration=json.loads((ASSESS/'calibration-assessment.json').read_text())
 known={str(x['claim_id']):x['known_verdict'] for x in json.loads((ASSESS/'calibration-packet.json').read_text())['claims']}
 cal_pred={str(x.get('claim_id')):x.get('verdict') for x in calibration.get('claims',[])} if isinstance(calibration,dict) else {}
 result={"schema_version":"scholar_pilot_assessment_summary.v1","status":"provisional_blinded_join_complete","rows":rows,"counts":{"reports":len(rows),"assessment_unresolved":sum(x['assessment_status']!='provisional_model_assessment' for x in rows),"cases":dict(collections.Counter(x.get('case_id') for x in rows)),"arms":dict(collections.Counter(x.get('arm') for x in rows))},"calibration":{"known":known,"predicted":cal_pred,"matches":sum(cal_pred.get(k)==v for k,v in known.items()),"n":len(known)},"limitations":["Assessment used the same model/provider family as generation and is not independent medical adjudication.","Blinded packet omitted arm labels, but case identity and source content were visible.","Small pilot; output counts and provisional scores do not establish population hallucination rates.","Parse failures and unresolved fields remain explicit; no structural or citation-count metric is used as a factual verdict."]}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result['counts'],ensure_ascii=False)); print('calibration',result['calibration'])
if __name__=='__main__':main()
