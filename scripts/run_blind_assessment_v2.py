#!/usr/bin/env python3
"""Run the corrected blinded assessment packet with one fixed rubric."""
from __future__ import annotations
import json,os,re,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113'
SYSTEM='''You are a provisional source-bound assessor. Use only the supplied report, question, and cited source passages. Do not infer missing facts from general knowledge. The method/arm identity is intentionally absent. For up to 8 substantive claims, return verdict supported, partially_supported, unsupported, contradicted, or unverifiable with source IDs and short evidence quotes. Then score: citation_entailment 0=no/1=partial/2=full; qualifier_retention 0=lost/1=partial/2=retained; important_content_coverage 0=major omission/1=partial/2=adequate; scope_compliance 0=missed/1=partial/2=met; usefulness 0=not useful/1=usable with gaps/2=useful. Use unverifiable when cited passages do not establish the claim. Return JSON only. This is not independent medical adjudication.'''
def call(endpoint,key,prompt,max_tokens=3000):
 payload={'model':'deepseek-v4-flash','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}],'temperature':0,'max_tokens':max_tokens}
 t=time.monotonic(); r=requests.post(endpoint.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload,timeout=(20,480)); elapsed=round(time.monotonic()-t,3); r.raise_for_status(); data=r.json(); content=((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''; return {'content':content,'elapsed_s':elapsed,'usage':data.get('usage'),'model':data.get('model'),'finish_reason':((data.get('choices') or [{}])[0].get('finish_reason'))}
def parse(s): return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',s.strip(),flags=re.I))
def main():
 endpoint=os.environ['LDR_LLM_OPENAI_ENDPOINT_URL']; key=os.environ['LDR_LLM_OPENAI_ENDPOINT_API_KEY']; packets=json.loads((D/'judge-inputs.json').read_text()); controls=json.loads((D/'calibration-inputs.json').read_text())
 calibration=call(endpoint,key,'Assess these calibration controls using the same rubric. Return {"controls":[{"control_id":"...","verdict":"supported|partially_supported|unsupported|contradicted|unverifiable"}]} and nothing else.\n'+json.dumps(controls,ensure_ascii=False),2000)
 try: cal_obj=parse(calibration['content']); cal_error=False
 except Exception: cal_obj={'raw':calibration['content']}; cal_error=True
 (D/'calibration-response.json').write_text(json.dumps(calibration,ensure_ascii=False,indent=2)+'\n'); (D/'calibration-assessment.json').write_text(json.dumps({'assessment':cal_obj,'parse_error':cal_error},ensure_ascii=False,indent=2)+'\n')
 results=[]
 for p in packets:
  prompt='Assess this blinded report. Include claim_assessments, the five numeric scores, omissions, and unresolved. Do not guess an algorithm arm.\n'+json.dumps({'blind_id':p['blind_id'],'question':p['question'],'report':p['report'],'cited_sources':p['cited_sources']},ensure_ascii=False)
  try:
   rec=call(endpoint,key,prompt); obj=parse(rec['content']); err=False
  except Exception as exc:
   rec=locals().get('rec',{}); obj={'error':str(exc)}; err=True
  row={'blind_id':p['blind_id'],'result_id':p['result_id'],'report_sha256':p['report_sha256'],'assessment':obj,'receipt':rec,'parse_error':err}; results.append(row); (D/f"{p['blind_id']}.json").write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'blind_id':p['blind_id'],'parse_error':err}),flush=True)
 manifest=json.loads((D/'manifest.json').read_text()); manifest.update({'status':'completed','completed':len(results),'parse_errors':sum(x['parse_error'] for x in results),'calibration_parse_error':cal_error}); (D/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
