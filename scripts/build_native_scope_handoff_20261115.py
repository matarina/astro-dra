"""Coordinator evidence packet, separate from independent adjudication."""
import json,hashlib,shutil,xml.etree.ElementTree as ET,difflib
from pathlib import Path
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def main():
 out=R/'source-view-native-coordinator-handoff-20261115-v1';out.mkdir(exist_ok=False)
 run=R/'source-view-native-model-20261115-v1/attempt';prior=R/'source-view-scope-writer-coordinator-handoff-20261115-v1/assessment-input'
 before=run/'actual_view_scope/original-report.md';after=run/'actual_view_scope/native-report.md';delta=''.join(difflib.unified_diff(before.read_text().splitlines(True),after.read_text().splitlines(True)))
 (out/'native-report-diff.patch').write_text(delta)
 sourcepack=read(run/'actual-source-pack.json');source9=next(s for s in sourcepack if str(s['index'])=='9');text=source9['fetched_content']
 paragraph,=[p for p in text.split('\n\n') if 'Cy7' in p and 'Ficoll' in p]
 xml=prior/'primary-source-9.xml';assert sha(xml)=='d2345fbffe9f3756391b6ff28070398a5f1043672e526665eb2a0baa7c88e0b5'
 tree=ET.fromstring(xml.read_bytes());parents={c:n for n in tree.iter() for c in n};primary=[]
 for n in tree.iter('p'):
  t=''.join(n.itertext())
  if 'Cy7' not in t and not t.startswith('Low‐density leukocytes were stained'):continue
  scope=[];c=n
  while c in parents:
   c=parents[c]
   if c.tag=='sec':
    title=c.find('title');scope.append(''.join(title.itertext()) if title is not None else '')
  primary.append(dict(text=t,original_xml=ET.tostring(n,encoding='unicode'),section_path=list(reversed(scope))))
 assert len(primary)>=2
 arm=run/'actual_view_scope';prompt=(arm/'call-002-prompt.txt').read_text();material=prompt.split('SUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0]
 confirmation=(arm/'call-003-prompt.txt').read_text();candidates=json.loads(confirmation.split('\nCandidates:\n',1)[1]);candidate,=candidates
 assert candidate['source_id']==9 and 'Cy7' not in candidate['source_context'] and paragraph not in material
 assert 'Cy7' not in material
 write(out/'source9-repair-evidence-chain.json',dict(scope='Coordinator source-grounded diagnosis, not independent correction/retention/new-error adjudication',
  source_identity={k:source9[k] for k in ['title','pmid','pmcid','doi']},primary_xml=str(xml),primary_xml_sha256=sha(xml),primary_paragraphs=primary,
  actual_shared_writer_and_native_input_paragraph=paragraph,
  first_review_prompt=dict(file=str(arm/'call-002-prompt.txt'),sha256=sha(arm/'call-002-prompt.txt'),actual_supplied_source_material=material,corresponding_paragraph_exposed=False),
  confirmation_prompt=dict(file=str(arm/'call-003-prompt.txt'),sha256=sha(arm/'call-003-prompt.txt'),candidates=candidates,corresponding_paragraph_exposed=False),
  confirmation_raw_response=(arm/'call-003-response.txt').read_text(),
  finding='Original MACS/CCR3/Cy7/Ficoll branch is present in actual shared acquired text and own primary Methods Donors C/D. Native selected excerpts omit it; reviewer calls it contradiction and proposes FACS; confirmation reuses the same incomplete source context and approves. Final experimental copy replaces that local branch with FACS, duplicating the preceding bullet. Later report summary still mentions MACS, so not total report-wide deletion.',
  transport_vs_semantics='Actual quote location and two model approvals did not establish an error in the original or same-analysis identity. This is an observed adverse local revision on this known report, not population/generalization or majority evidence.',
  no_new_scientific_rule=True,independent_correction_credit=0))
 assessment=out/'assessment-input';assessment.mkdir()
 mapping={}
 for label,armname,filename in [('A','actual_view_scope','native-report.md'),('B','record_scope','native-report.md'),('C','actual_view_scope','original-report.md'),('D','record_scope','original-report.md')]:
  original=run/armname/filename;target=assessment/f'document-{label}.md';shutil.copyfile(original,target);mapping[label]=dict(arm=armname,file=filename,sha256=sha(target))
 for name in ['original-question.txt','sources.json','generation-source-material.json','primary-index.json',*[p.name for p in prior.glob('primary-source-*.xml')]]:
  shutil.copyfile(prior/name,assessment/name)
 write(assessment/'assessment-status.json',dict(status='UNASSESSED',scope='Four complete documents, question, actual shared generation materials, identity records and additional primary XML. Document mapping and coordinator findings kept outside. Requires independent original-source corrections, useful retention and new-error assessment; do not infer paper completeness or image inspection.',independent_correction_credit=0))
 write(out/'document-mapping.json',mapping)
 results=[read(run/a/'result.json') for a in ['record_scope','actual_view_scope']]
 write(out/'decision.json',dict(scope=__doc__,decision='DEFER semantic/production adoption; known native repair loses supported procedural content locally',
  native_calls=sum(r['model_calls'] for r in results),results=results,new_independent_correction_credit=0,
  source3_amendment=str(R/'source3-quantity-scope-amendment-20261115-v2/amendment.json'),
  source_query_offline=str(R/'native-source-query-offline-20261115-v2/receipt.json'),
  next_work='Bounded generic confirmation-context candidate: inspect complete acquired source for affected source IDs where context budget permits; preserve source section/analysis branches and explicit unshown status where it does not. Existing prompts already instruct against absence-as-contradiction; do not merely repeat them or add science-specific terms. Validate with source-matched unchanged/report controls before another complete Writer/native evaluation. No deployment or blind quality credit.',
  limitations='Different report inputs; native-stage diagnostic only, no retrieval/full synthesis/publication. Fixed supplement network; endpoint alias not verified checkpoint. Independent assessment pending; reserved controls untouched.'))
 for p in [Path(__file__),Path('scripts/run_source_view_native_pair_20261115.py'),Path('scripts/audit_source_view_native_pair_20261115.py'),Path('scripts/probe_native_source_queries_20261115.py')]:shutil.copyfile(p,out/p.name)
 print(json.dumps(dict(handoff=str(out),assessment_documents=4,independent_correction_credit=0)))
if __name__=='__main__':main()
