#!/usr/bin/env python3
"""Prepare a genuinely blinded, source-bound assessment packet v2."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113'
RESULT_ROOTS=[ROOT/'evaluation/scholar-controlled-pilot-corrected-20261112/results',ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112/results']

def sha(s: str)->str:return hashlib.sha256(s.encode()).hexdigest()
def cited_ids(text):
 out=[]
 for m in re.finditer(r'\[\[?(\d+)\]?\]',text or ''):
  i=int(m.group(1))
  if i not in out:out.append(i)
 return out
def fetch_text(url):
 r=requests.get(url,headers={'User-Agent':'LDR assessment evidence/2026-11-13'},timeout=60); r.raise_for_status()
 soup=BeautifulSoup(r.text,'html.parser')
 for t in soup(['script','style','noscript']):t.decompose()
 text='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())
 return text,r.url,r.status_code
def build_reports():
 items=[]
 for root in RESULT_ROOTS:
  for p in sorted(root.glob('*/**/result.json')):
   d=json.loads(p.read_text())
   if d.get('status')!='completed' or not d.get('body'):continue
   if d.get('case_id') in {'new-certolizumab','new-xlinked-epilepsy'}: continue
   source_ref=d['source_file']; source_ref=source_ref.replace('/workspace/','',1) if source_ref.startswith('/workspace/') else source_ref
   if d.get('case_id') in {'new-art001-gene-editing','new-crustacean-single-cell'}:
    corrected=ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112/identity-corrected-20261113'/f"{d['case_id']}-base.json"
    if corrected.exists(): source_ref=str(corrected.relative_to(ROOT))
   sources=json.loads((ROOT/source_ref).read_text()); by={int(s['index']):s for s in sources if str(s.get('index','')).isdigit()}
   records=[]
   for i in cited_ids(d['body']):
    if i in by:
     s=by[i]; records.append({'index':i,'title':s.get('title'),'pmid':s.get('pmid'),'doi':s.get('doi'),'evidence_type':s.get('content_type') or 'abstract','text':s.get('full_content') or s.get('abstract') or s.get('content') or ''})
   result_id=sha(str(p.relative_to(ROOT)))[:16]
   items.append({'blind_id':'judge-'+result_id,'result_id':result_id,'case_id':d.get('case_id'),'question':d.get('query'),'report':d['body'],'cited_sources':records,'source_sha256':d.get('source_sha256'),'report_sha256':sha(d['body']),'result_path':str(p.relative_to(ROOT))})
 return items
def build_calibration():
 controls=[
  ('cal-01','**分选**：FACS分选 [81]','supported','https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2023.1151754/full','Human lung mast cells were single cell sorted into 384 well plate using a BD FACS Fusion. Single cell RNA sequencing libraries were prepared and sequenced using Smart-seq2 protocol.'),
  ('cal-02','- [33] ANXA7 in CRC — 仅单细胞转录组挖掘','contradicted','https://link.springer.com/article/10.1186/s12951-026-04915-z',None),
  ('cal-03',"| **单细胞3' RNA-seq** | 标准高通量单细胞转录组 | 鸡外周血白细胞研究使用单细胞3' RNA-seq [55] |",'partially_supported','https://link.springer.com/article/10.1186/s12864-024-10044-4',None)]
 inputs=[]; answer=[]
 for cid,claim,label,url,passage in controls:
  if passage is None: passage,final,status=fetch_text(url)
  else: final,status=url,200
  inputs.append({'control_id':cid,'claim':claim,'source':{'url':final,'status':status,'text':passage}})
  answer.append({'control_id':cid,'verdict':label,'source_url':final,'source_sha256':sha(passage)})
 return inputs,answer
def main():
 OUT.mkdir(parents=True,exist_ok=True); reports=build_reports(); calibration,answer=build_calibration()
 (OUT/'judge-inputs.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
 (OUT/'calibration-inputs.json').write_text(json.dumps(calibration,ensure_ascii=False,indent=2)+'\n')
 (OUT/'answer-key-private.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
 manifest={'schema_version':'scholar_blind_assessment_v2.v1','status':'frozen_before_v2_judging','reports':len(reports),'calibration_controls':len(calibration),'arm_settings_included':False,'known_verdicts_included':False,'label_revealing_scope_included':False,'opaque_mapping':True,'rubric':{'verdicts':['supported','partially_supported','unsupported','contradicted','unverifiable'],'citation_entailment_scale':'0=no/1=partial/2=full','qualifier_retention_scale':'0=lost/1=partial/2=retained','important_content_coverage_scale':'0=major omission/1=partial/2=adequate','scope_compliance_scale':'0=missed/1=partial/2=met','usefulness_scale':'0=not useful/1=usable with gaps/2=useful'},'limitations':['same model/provider family as generation','not independent medical adjudication','source-bound cited evidence is not corpus recall','answer key stored separately']}
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'reports':len(reports),'calibration':len(calibration)},ensure_ascii=False))
if __name__=='__main__':main()
