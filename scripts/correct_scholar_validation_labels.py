#!/usr/bin/env python3
"""Record the supervisory correction for the mislabelled old validation families."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'evaluation/scholar-controlled-pilot-corrected-20261112/manifest.json'
EX=Path('/data1/maxw/.local/state/dra-hourly-monitor/known-used-task-exclusions-20261112.json')
OUT=ROOT/'evaluation/scholar-controlled-pilot-corrected-20261112/label-correction-20261112.json'
def main():
 old=json.loads(OLD.read_text()); ex=json.loads(EX.read_text())
 affected=[]
 for case in old.get('new_cases',[]):
  stem={'new-certolizumab':'f_ea0305f6eefa','new-xlinked-epilepsy':'f_5bfd4ff2a26d'}.get(case)
  if stem: affected.append({'case_id':case,'family_id':stem,'corrected_role':'prior_evaluated_regression_only','new_validation':False,'reason':'Family has completed and annotated baseline/candidate reports in the verified exclusion inventory.'})
 result={'schema_version':'scholar_validation_label_correction.v1','status':'old_manifest_preserved_but_new_claims_retracted','superseded_manifest':str(OLD.relative_to(ROOT)),'exclusion_inventory_sha256':hashlib.sha256(EX.read_bytes()).hexdigest(),'affected':affected,'preserved_results':'Retain files for regression; exclude from new-task denominators.','replacement_validation':'evaluation/scholar-controlled-pilot-corrected-v2-20261112/manifest.json'}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
