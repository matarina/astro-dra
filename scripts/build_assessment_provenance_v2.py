#!/usr/bin/env python3
"""Record generation/assessment/source hashes for corrected blinded v2."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113'; OUT=ROOT/'evaluation/scholar-strategy-20261112/assessment-provenance-v2-20261113.json'
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 packets=json.loads((D/'judge-inputs.json').read_text()); rows=[]
 for p in packets:
  result=ROOT/p['result_path']; rd=json.loads(result.read_text()); generation_source=ROOT/rd['source_file'].replace('/workspace/','',1) if str(rd['source_file']).startswith('/workspace/') else ROOT/rd['source_file']; assessment_source=generation_source
  if p['case_id'] in {'new-art001-gene-editing','new-crustacean-single-cell'}:
   assessment_source=ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112/identity-corrected-20261113'/f"{p['case_id']}-base.json"
  judge_file=D/f"{p['blind_id']}.json"
  rows.append({'blind_id':p['blind_id'],'result_id':p['result_id'],'case_id':p['case_id'],'generation_result_file':str(result.relative_to(ROOT)),'generation_result_sha256':h(result),'generation_source_file':str(generation_source.relative_to(ROOT)),'generation_source_sha256':h(generation_source),'assessment_source_file':str(assessment_source.relative_to(ROOT)),'assessment_source_sha256':h(assessment_source),'judge_input_sha256':h(D/'judge-inputs.json'),'assessment_file':str(judge_file.relative_to(ROOT)),'assessment_file_sha256':h(judge_file),'report_sha256':p['report_sha256'],'claim_count':len(json.loads(judge_file.read_text())['assessment'].get('claim_assessments',[])),'claim_protocol_deviation':len(json.loads(judge_file.read_text())['assessment'].get('claim_assessments',[]))>8})
 out={'schema_version':'scholar_assessment_provenance_v2.v1','status':'complete','packet_file':str((D/'judge-inputs.json').relative_to(ROOT)),'packet_sha256':h(D/'judge-inputs.json'),'rows':rows,'scope':'Generation and corrected assessment source identities; does not rewrite original generation receipts.'}
 OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'rows':len(rows),'new_identity_source_distinct':sum(x['generation_source_sha256']!=x['assessment_source_sha256'] for x in rows)},ensure_ascii=False))
if __name__=='__main__':main()
