#!/usr/bin/env python3
import json, os, re, time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-20261112'
def main():
 p=next(x for x in json.loads((D/'packets.json').read_text()) if x['blind_id']=='blind-11')
 prompt='''Assess this report against its cited source. Return ONLY one compact JSON object with exactly these keys: supported (integer), partially_supported (integer), unsupported (integer), contradicted (integer), unverifiable (integer), citation_entailment (0-2), qualifier_retention (0-2), important_content_coverage (0-2), scope_compliance (0-2), usefulness (0-2), omissions (array of short strings), unresolved (array of short strings). Do not include quotes, claim text, or source IDs. Use only supplied source text. This is provisional, not independent medical adjudication.\n'''+json.dumps(p,ensure_ascii=False)
 payload={'model':'deepseek-v4-flash','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':1000}
 started=time.monotonic(); r=requests.post(os.environ['LDR_LLM_OPENAI_ENDPOINT_URL'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+os.environ['LDR_LLM_OPENAI_ENDPOINT_API_KEY']},json=payload,timeout=(20,480)); r.raise_for_status(); data=r.json(); content=((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
 clean=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip(),flags=re.I); assessment=json.loads(clean)
 row={'blind_id':'blind-11','case_id':p['case_id'],'report_sha256':p['report_sha256'],'receipt':{'content':content,'elapsed_s':round(time.monotonic()-started,3),'usage':data.get('usage'),'model':data.get('model')},'assessment':assessment,'parse_error':False,'retry':'minimal'}
 (D/'blind-11-minimal.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(row,ensure_ascii=False))
if __name__=='__main__': main()
