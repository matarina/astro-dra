#!/usr/bin/env python3
"""Freeze a source-scoped, blinded next-phase evaluation packet.

This script does not call a model or alter production. It snapshots selected PubMed
records, verifies that reserved identities are absent from existing evaluation
artifacts, and builds a public blinded packet plus a separate private arm map.
"""
from __future__ import annotations
import argparse, hashlib, json, re, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/hallucination-next-phase-20261113'
SOURCE_XML=OUT/'sources/pubmed-selected-20261113.xml'

def sha256_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha256_file(p:Path)->str:return sha256_bytes(p.read_bytes())
def dump(p:Path,obj:Any):
 p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
def text(el): return ''.join(el.itertext()).strip() if el is not None else ''

def xml_records():
 root=ET.fromstring(SOURCE_XML.read_bytes()); out=[]
 for a in root.findall('.//PubmedArticle'):
  pmid=text(a.find('.//PMID'))
  title=text(a.find('.//ArticleTitle'))
  abst=[]
  for x in a.findall('.//Abstract/AbstractText'):
   lab=x.attrib.get('Label'); val=text(x); abst.append((f'{lab}: ' if lab else '')+val)
  ids={x.attrib.get('IdType'):text(x) for x in a.findall('.//ArticleId') if text(x)}
  journal=text(a.find('.//Journal/Title'))
  pubdate=text(a.find('.//PubDate/Year')) or text(a.find('.//PubDate/MedlineDate'))
  pts=[text(x) for x in a.findall('.//PublicationType')]
  url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/' if pmid else None
  abstract=' '.join(abst)
  out.append({'pmid':pmid,'doi':ids.get('doi'),'title':title,'journal':journal,
              'pubdate':pubdate,'publication_types':pts,'link':url,'abstract':abstract,
              'snippet':f'Title: {title}\nJournal: {journal}\nDate: {pubdate}\nDOI: {ids.get("doi", "unknown")}\nPMID: {pmid}\nPublication types: {", ".join(pts)}\nEvidence level: abstract\nAbstract: {abstract}',
              'source_engine':'pubmed','evidence_level':'abstract','content_type':'abstract',
              'scope':'PubMed abstract snapshot fetched 2026-11-13; no full text claimed'})
 return out

def all_existing_pmids():
 seen=set()
 for p in ROOT.glob('evaluation/**/*.json'):
  if str(OUT) in str(p): continue
  try:d=json.loads(p.read_text())
  except Exception:continue
  def rec(x):
   if isinstance(x,dict):
    for k,v in x.items():
     if k.lower()=='pmid' and v is not None:
      m=re.search(r'\b(\d{6,9})\b',str(v));
      if m:seen.add(m.group(1))
     rec(v)
   elif isinstance(x,list):
    for v in x:rec(v)
  rec(d)
 return seen

def read_input(name): return ROOT/name

def source_hash(p): return sha256_file(ROOT/p)

def historical_case(case_id, input_name, reports, failure_stage, question, items, notes):
 source_p=read_input(input_name)
 data=json.loads(source_p.read_text())
 return {'case_id':case_id,'status':'historical_replay_only','failure_stage':failure_stage,
  'question':question,'requested_information':items,'source_file':str(source_p.relative_to(ROOT)),
  'source_sha256':source_hash(source_p),'source_count':len(data),'source_scope':'original frozen source record and abstract/excerpts as supplied to the prior run; no new retrieval',
  'reports':reports,'notes':notes}

def make_packet(case, variant, result_path):
 d=json.loads((ROOT/result_path).read_text()); source_path=ROOT/case['source_file']; sources=json.loads(source_path.read_text())
 report=d.get('body','')
 rid=sha256_bytes((case['case_id']+'|'+variant+'|'+d.get('report_sha256','')).encode())[:16]
 return {'blind_id':'blind-'+rid,'case_id':case['case_id'],'variant':variant,
         'question':case['question'],'requested_information':case['requested_information'],
         'report':report,'report_sha256':sha256_bytes(report.encode()),
         'source_scope':{'source_sha256':case['source_sha256'],'source_count':len(sources),'evidence_policy':case['source_scope']},
         'source_records':[{'index':x.get('index'),'title':x.get('title'),'link':x.get('link'),'doi':x.get('doi'),'pmid':x.get('pmid'),'journal':x.get('journal'),'pubdate':x.get('pubdate'),'publication_types':x.get('publication_types'),'evidence_level':x.get('evidence_level','abstract'),'abstract':x.get('abstract'),'snippet':x.get('snippet'),'source_engine':x.get('source_engine')} for x in sources],
         'assessment_fields':{'claim_verdicts':None,'citation_entailment':None,'qualifier_retention':None,'important_content_coverage':None,'scope_compliance':None,'usefulness':None,'unsupported_claims':None,'contradicted_claims':None,'unverifiable_claims':None,'latency_seconds':None,'tokens':None,'reviewer_notes':''}}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--write',action='store_true'); args=ap.parse_args()
 records=xml_records(); by={x['pmid']:x for x in records}; selected=set(by)
 existing=all_existing_pmids(); overlap=sorted(selected & existing)
 if overlap: raise SystemExit(f'reserved PMID overlap with existing evaluation artifacts: {overlap}')
 for x in records: dump(OUT/'sources'/f"pmid-{x['pmid']}.json",x)
 new=[
  {'case_id':'new-crispr-clinical-safety','topic':'gene editing safety and translational evidence',
   'question':'Compare what these sources establish about CRISPR/Cas genome-editing safety, efficacy and translational readiness. Separate clinical-trial evidence, preclinical/IND-enabling evidence and review-level synthesis; identify populations/models, intervention, endpoints, limitations and what remains unknown.',
   'pmids':['41810550','39086133','39413163'],
   'requested_information':['study type and evidence level per paper','population/model and intervention','safety/off-target or efficacy endpoints','limitations and unresolved risks','explicit separation of direct findings from review synthesis']},
  {'case_id':'new-spatial-neuro-oncology','topic':'single-cell and spatial transcriptomics in tumor immunity',
   'question':'Compare how these studies use single-cell and spatial transcriptomics to characterize tumor immunity. Report cohort/model, modalities and platform when supplied, key immune findings, validation, and limits. Do not infer platform, causality or clinical benefit when the abstract does not state it.',
   'pmids':['42908192','42677450','42552377'],
   'requested_information':['cohort/model and specimen','single-cell/spatial modalities and named platform','immune/TME findings','validation and outcome evidence','unknown or abstract-only details']}
 ]
 for task in new:
  task['source_pack']=[f'sources/pmid-{p}.json' for p in task['pmids']]
  task['source_pack_sha256']=[sha256_file(OUT/f'sources/pmid-{p}.json') for p in task['pmids']]
  task['scope']='Three PubMed abstract snapshots fetched 2026-11-13; all records are source-visible, but full text/methods/platform details are unavailable unless stated in the abstract.'
 hist=[
  historical_case('historical-immune','evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-immune-base.json',
   {'baseline':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-immune/baseline_with_draft/result.json','candidate_a':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-immune/candidate_a_with_draft/result.json'},
   'available_but_possible_scientific_misreading','Summarize immune-cell studies and preserve population, methods and findings without merging distinct papers.',
   ['population/model for each cited study','assay/modality and main finding','qualifiers and unresolved evidence'],
   'Historical adjudicated claims include method/population attribution and IL-5 subject separation. Labels are regression evidence, not prevalence estimates.'),
  historical_case('historical-if','evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-if-base.json',
   {'baseline':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-if/baseline_with_draft/result.json','candidate_a':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-if/candidate_a_with_draft/result.json'},
   'missing_decisive_text_and_document_mixing','Identify 2026 tumor papers containing both single-cell and spatial transcriptomics and report platform/metadata only when supplied.',
   ['study identity and publication type','single-cell and spatial modalities','platform and IF state','missing evidence/unknown fields'],
   'Prior visibility audit found decisive spatial/platform details missing or partial for several claims; do not count this as a model error until matched evidence runs.'),
  historical_case('historical-adipose','evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-adipose-base.json',
   {'baseline':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-adipose/baseline_with_draft/result.json','candidate_a':'evaluation/scholar-controlled-pilot-corrected-20261112/results/historical-adipose/candidate_a_with_draft/result.json'},
   'cross_paper_document_inconsistency','Survey high-impact adipose spatial-transcriptomics research while distinguishing spatial from non-spatial studies and preserving requested metadata limits.',
   ['which studies actually use spatial transcriptomics','platform when stated','study type and journal identity','important omissions and evidence limitations'],
   'Existing assessment noted many non-spatial studies and missing systematic publication-type/IF classification; retained as a document-level regression.'),
 ]
 manifest={'schema_version':'hallucination_next_phase_eval_freeze.v1','created_utc':datetime.now(timezone.utc).isoformat(),
  'status':'frozen_before_next_phase_model_calls','production_changed':False,'model_calls_in_freeze':0,
  'historical_cases':hist,'reserved_new_cases':new,
  'reserved_identity_check':{'selected_pmids':sorted(selected),'overlap_with_existing_evaluation_artifacts':overlap,'scope':'recursive PMID scan of evaluation/**/*.json excluding this freeze directory; exact identity only, not semantic novelty','result':'no_exact_overlap'},
  'controls':{'generation_model':'DeepSeek V4 Flash as current production baseline; candidate settings must be matched per arm','temperature':0,'max_output_tokens':5000,'native_fact_consistency':True,'save_time_citation_audit':False,'source_pool':'PubMed/SearXNG/Europe PMC production pool; freeze uses only the listed PubMed snapshots','search_and_tool_budget':'must be identical between arms; no live calls in this freeze','review_budget':'must be identical between arms; blind assessment pending'},
  'assessment_protocol':{'blind_public_packet':'packets/blinded-assessment-packet.json','private_arm_map':'packets/arm-map-private.json','verdicts':['supported','partially_supported','unsupported','contradicted','unverifiable'],'required_dimensions':['claim verdicts','citation entailment','qualifier/counterevidence retention','important-content coverage','scope compliance','usefulness','latency/tokens'],'rules':['source-visible facts must be scoped to the supplied snapshot','unknown/abstract-only access must be preserved','structural validity, citation count or report length is not semantic accuracy','unresolved labels remain unresolved','no automatic deletion or publication gate']},
  'exclusions':['patatin and Dst1 were previously evaluated','certolizumab and X-linked epilepsy were previously generated/assessed','ART001 and crustacean single-cell tasks were previous new-task validation','KRAS template examples are excluded from the feedback denominator'],
  'limitations':['reserved tasks are selected from current PubMed snapshots and are exact-identity novel only; semantic novelty is not proven','abstract-only sources cannot test full-text passage acquisition','no model calls or quality labels are part of this freeze','independent medical adjudication is not yet available']}
 dump(OUT/'manifest.json',manifest)
 # Public blinded packet: historical baseline/A reports only; no arm labels.
 packets=[]; mapping=[]
 for c in hist:
  for variant,path in c['reports'].items():
   p=make_packet(c,variant,path); packets.append({k:v for k,v in p.items() if k not in ('case_id','variant')}); mapping.append({'blind_id':p['blind_id'],'case_id':c['case_id'],'variant':variant,'result_path':path,'report_sha256':p['report_sha256']})
 dump(OUT/'packets/blinded-assessment-packet.json',{'schema_version':'blinded_packet.v1','status':'pending_assessment','blinding':'arm/model/algorithm labels removed from public entries; case IDs are retained for source grouping but not arm identity','packets':packets})
 dump(OUT/'packets/arm-map-private.json',{'schema_version':'private_arm_map.v1','status':'do_not_include_in_judge_prompt','rows':mapping})
 readme='''# Hallucination next-phase evaluation freeze (2026-11-13)\n\nThis directory freezes a small, source-scoped pilot before any next-phase model calls. It contains three historical regression cases and two exact-identity-new multi-paper biomedical tasks. The freeze itself made **zero model calls** and did not change or deploy production.\n\n## Historical cases\n\n- `historical-immune`: available evidence with possible scientific/method attribution errors.\n- `historical-if`: missing decisive spatial/platform text plus document-level mixing risk.\n- `historical-adipose`: cross-paper and document-consistency risk (spatial versus non-spatial studies).\n\nThe historical source files, report receipts, and hashes are in `manifest.json`. Prior labels are regression evidence only; they are not a prevalence estimate or independent medical gold.\n\n## Reserved new tasks\n\n- `new-crispr-clinical-safety`: three PubMed abstracts comparing review, IND-enabling and translational genome-editing evidence.\n- `new-spatial-neuro-oncology`: three PubMed abstracts covering single-cell/spatial tumor-immunity studies.\n\nThe source snapshots are in `sources/`. Each is abstract-scoped; absent full text, methods, platform or clinical details must remain unknown. The identity check is exact PMID matching against existing `evaluation/**/*.json` artifacts and does not prove semantic novelty.\n\n## Assessment\n\n`packets/blinded-assessment-packet.json` contains six historical reports with arm/model labels removed. The separate `packets/arm-map-private.json` is retained for analysis and must not be sent to a judge. Reserved new-task reports are intentionally absent until matched baseline/candidate runs are completed. Use the verdicts supported, partially supported, unsupported, contradicted, or unverifiable; assess citation entailment, qualifier/counterevidence retention, requested-information coverage, scope, usefulness, and resource cost. Do not treat citation counts, structural checks, report length or native self-review as medical accuracy.\n\nThe protocol requires matched question, source scope, model, tool/review budgets and output budget for baseline and each candidate. Keep acquisition changes separate from ranking/verification changes. Preserve unknowns, failed runs and raw receipts. No automatic deletion, publication gate, save-time citation audit or production deployment is permitted.\n'''
 (OUT/'README.md').write_text(readme)
 print('wrote',OUT)
if __name__=='__main__':main()
