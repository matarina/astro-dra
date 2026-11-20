#!/usr/bin/env python3
"""Retry only parse-failed blinded assessment packets with a compact schema."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-20261112'
RUBRIC='''You are a provisional source-bound assessor. Use only the supplied report and cited sources. Return compact JSON only, no prose: {"claim_assessments":[{"claim":"...","verdict":"supported|partially_supported|unsupported|contradicted|unverifiable","source_ids":[1],"evidence_quote":"..."}],"citation_entailment":0,"qualifier_retention":0,"important_content_coverage":0,"scope_compliance":0,"usefulness":0,"omissions":[],"unresolved":[]}. Sample at most 8 substantive claims. Unknown source detail is unverifiable, not contradicted. This is not independent medical adjudication.'''

def main():
 endpoint=os.environ['LDR_LLM_OPENAI_ENDPOINT_URL'].rstrip('/'); key=os.environ['LDR_LLM_OPENAI_ENDPOINT_API_KEY']
 packets=json.loads((DIR/'packets.json').read_text())
 for bid in ['blind-06','blind-11']:
  packet=next(x for x in packets if x['blind_id']==bid)
  prompt='Assess this blinded report compactly. Do not guess its algorithm arm.\n'+json.dumps(packet,ensure_ascii=False)
  payload={'model':'deepseek-v4-flash','messages':[{'role':'system','content':RUBRIC},{'role':'user','content':prompt}], 'temperature':0,'max_tokens':5000}
  started=time.monotonic(); r=requests.post(endpoint+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=(20,480)); elapsed=round(time.monotonic()-started,3); r.raise_for_status(); data=r.json(); content=((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
  clean=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip(),flags=re.I)
  try: assessment=json.loads(clean); parse_error=False
  except Exception: assessment={'raw':content}; parse_error=True
  row={'blind_id':bid,'case_id':packet['case_id'],'report_sha256':packet['report_sha256'],'receipt':{'content':content,'elapsed_s':elapsed,'usage':data.get('usage'),'model':data.get('model'),'finish_reason':((data.get('choices') or [{}])[0].get('finish_reason'))},'assessment':assessment,'parse_error':parse_error,'retry':True}
  (DIR/(bid+'-retry.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({'blind_id':bid,'parse_error':parse_error,'chars':len(content)}))
if __name__=='__main__': main()
