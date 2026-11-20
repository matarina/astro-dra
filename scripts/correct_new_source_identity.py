#!/usr/bin/env python3
"""Correct selected PubMed ArticleId DOI metadata without rewriting runs."""
from __future__ import annotations
import hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'evaluation/scholar-controlled-pilot-corrected-v2-20261112'
OUT=BASE/'identity-corrected-20261113'; OUT.mkdir(parents=True,exist_ok=True)
def main():
 rows=[]
 for case,pmid in [('new-art001-gene-editing','42063796'),('new-crustacean-single-cell','42555179')]:
  xml=next((p for p in (BASE/'inputs').glob(f'{pmid}*.xml')),None)
  root=ET.fromstring(xml.read_bytes()); article=root.find('.//PubmedArticle'); selected=[]
  for aid in article.findall('./PubmedData/ArticleIdList/ArticleId') if article is not None else []: selected.append((aid.attrib.get('IdType'),aid.text or ''))
  doi=next((v for k,v in selected if k=='doi'),'')
  old_path=BASE/'inputs'/f'{case}-base.json'; data=json.loads(old_path.read_text()); old=data[0].get('doi'); data[0]['doi']=doi; data[0]['identity_correction']='PubmedData/ArticleIdList scoped to selected article'
  new_path=OUT/f'{case}-base.json'; new_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
  rows.append({'case_id':case,'pmid':pmid,'old_doi':old,'correct_doi':doi,'selected_article_ids':selected,'old_input_sha256':hashlib.sha256(old_path.read_bytes()).hexdigest(),'corrected_input_sha256':hashlib.sha256(new_path.read_bytes()).hexdigest(),'report_text_contains_old_doi':any(old in p.read_text(errors='ignore') for p in (BASE/'results'/case).glob('*/report.md'))})
 result={'schema_version':'new_source_identity_correction.v1','status':'metadata_corrected_without_generation_rerun','rows':rows,'reason':'Reports contain no DOI strings; old generation outputs retain original metadata hashes and are not relabelled as corrected runs. Corrected identity is used for future assessment/overlap records.','source_xml_preserved':True}
 (OUT/'identity-correction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
