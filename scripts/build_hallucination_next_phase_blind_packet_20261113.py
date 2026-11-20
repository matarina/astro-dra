#!/usr/bin/env python3
"""Build a blinded assessment packet from completed next-phase result receipts.

Input is a JSON list of records with case_id, arm, result_path, source_file,
source_sha256 and (optionally) settings. This is packaging only: it does not
call a model, score claims, or alter reports.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'evaluation/hallucination-next-phase-20261113'
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('receipt'); ap.add_argument('--out',default='evaluation/hallucination-next-phase-20261113/packets/blinded-assessment-packet-generated.json'); ap.add_argument('--private-out',default='evaluation/hallucination-next-phase-20261113/packets/arm-map-generated-private.json'); a=ap.parse_args()
 rows=json.loads(Path(a.receipt).read_text());
 if not isinstance(rows,list) or not rows: raise SystemExit('receipt must be a non-empty JSON list')
 # Matched controls: same source identity and settings for every arm within a case.
 by={}
 for r in rows:
  for k in ('case_id','arm','result_path','source_file','source_sha256'):
   if not r.get(k): raise SystemExit(f'missing {k}')
  d=json.loads((ROOT/r['result_path']).read_text());
  if d.get('source_sha256') and d['source_sha256']!=r['source_sha256']: raise SystemExit(f'source hash mismatch {r["result_path"]}')
  by.setdefault(r['case_id'],[]).append(r)
 for case,rs in by.items():
  source={(x['source_file'],x['source_sha256']) for x in rs}
  if len(source)!=1: raise SystemExit(f'unmatched source scope for {case}')
  settings={json.dumps(x.get('settings',{}),sort_keys=True) for x in rs}
  if len(settings)>1: raise SystemExit(f'unmatched settings for {case}')
 packets=[]; private=[]
 for r in rows:
  d=json.loads((ROOT/r['result_path']).read_text()); report=d.get('body',''); blind='blind-'+sha(r['case_id']+'|'+r['arm']+'|'+sha(report))[:16]
  source=json.loads((ROOT/r['source_file']).read_text())
  packets.append({'blind_id':blind,'case_id':r['case_id'],'question':r.get('question',d.get('query')),'requested_information':r.get('requested_information',[]),'report':report,'report_sha256':sha(report),'source_scope':{'source_sha256':r['source_sha256'],'source_count':len(source),'evidence_policy':r.get('source_scope','supplied source snapshot')},'source_records':source,'assessment_fields':{'claim_verdicts':None,'citation_entailment':None,'qualifier_retention':None,'important_content_coverage':None,'scope_compliance':None,'usefulness':None,'unsupported_claims':None,'contradicted_claims':None,'unverifiable_claims':None,'latency_seconds':None,'tokens':None,'reviewer_notes':''}})
  private.append({'blind_id':blind,'case_id':r['case_id'],'arm':r['arm'],'result_path':r['result_path'],'source_file':r['source_file'],'source_sha256':r['source_sha256']})
 Path(ROOT/a.out).write_text(json.dumps({'schema_version':'blinded_packet.v2','status':'pending_assessment','packets':packets},ensure_ascii=False,indent=2)+'\n')
 Path(ROOT/a.private_out).write_text(json.dumps({'schema_version':'private_arm_map.v2','status':'do_not_include_in_judge_prompt','rows':private},ensure_ascii=False,indent=2)+'\n')
 print(f'wrote {len(packets)} blinded packets; no model calls')
if __name__=='__main__':main()
