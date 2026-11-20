"""Coordinator handoff: structured source-field association experiment, no complete report correction."""
import ast,json,hashlib,shutil,xml.etree.ElementTree as ET
from pathlib import Path
R=Path('evaluation/frontier-strategy-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 from research_verify import canonical_fields
 from research_verify.request_additions import parse_request_plan
 base=R/'multi-requirement-baseline-code-20261115-v1/canonical_fields.py';assert base.read_bytes()==(R/'acquired-confirmation-model-20261115-v1/attempt/code/local_deep_research/research_verify/canonical_fields.py').read_bytes()
 prior=R/'request-canonical-if-model-20261114-v1/attempt';case,=read(R/'source-span-if-original-inputs-20261115-v1/case-manifest.json')['cases'];units=read(prior/'source-units.json');req=parse_request_plan((prior/'call-00-response.txt').read_text(),case['query'])
 namespace=dict(vars(canonical_fields));tree=ast.parse(base.read_text());fn,=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='parse_unit_fields'];exec(compile(ast.Module(body=[fn],type_ignores=[]),str(base),'exec'),namespace)
 raw=(prior/'call-01-response.txt').read_text();assert namespace['parse_unit_fields'](raw,req,units)==canonical_fields.parse_unit_fields(raw,req,units)
 out=R/'multi-requirement-if-coordinator-handoff-20261115-v2';out.mkdir(exist_ok=False);assessment=out/'assessment-input';assessment.mkdir()
 model=R/'multi-requirement-if-model-20261115-v1/attempt';mapping={}
 for label,index in [('A',1),('B',0)]:
  path=model/f'call-{index:02d}-response.txt';shutil.copyfile(path,assessment/f'reading-{label}.json.txt');mapping[label]=dict(arm='multiple_requirements' if index else 'single_requirement',sha256=sha(path))
 (assessment/'original-question.txt').write_text(case['query']);shutil.copyfile(prior/'source-units.json',assessment/'actual-source-units.json')
 xml=R/'field-comparison-if-review-packet-20261114-v1/source5-original-article.xml';assert sha(xml)=='09cddeb8e7da337ce6643cddbf689e90b0c1321b454403a9eb009d85955f9f2f';shutil.copyfile(xml,assessment/'primary-source.xml')
 write(assessment/'status.json',dict(status='UNASSESSED',scope='Two fallible source-field readings, not complete reports. Same source5 namespace/actual units. No original report, feedback, coordinator findings or mapping supplied here. Original question asks20eligible papers; these two readings cover ONE known paper only. Independent original-source scope/unit/quantity/new-error assessment required.'))
 write(out/'mapping.json',mapping)
 evidence=[];tree=ET.fromstring(xml.read_bytes());parents={c:n for n in tree.iter() for c in n}
 for n in tree.iter('p'):
  text=''.join(n.itertext())
  if 'female Visium' not in text and not ('female sections' in text and 'Visium HD FFPE' in text):continue
  headings=[];cur=n
  while cur in parents:
   cur=parents[cur]
   if cur.tag=='sec':
    title=cur.find('title');headings.append(''.join(title.itertext()) if title is not None else '')
  evidence.append(dict(text=text,section_path=list(reversed(headings)),original_xml=ET.tostring(n,encoding='unicode')))
 assert len(evidence)==2
 caption_units=[u for u in units if 'female sections' in u['text'] and 'Visium HD FFPE' in u['text']];assert len(caption_units)==1
 write(out/'coordinator-evidence.json',dict(scope='Known-source diagnosis, not independent adjudication',primary_xml_sha256=sha(xml),primary_paragraphs=evidence,actual_supplied_caption_units=caption_units,
  observation='SUPERSEDES v1 broader uncertainty: the Results paragraph alone calls the reused female data Visium, but ORIGINAL FIGURE1E CAPTION explicitly calls the three identified female sections and male samples Visium HD FFPE spatial maps. This caption is present in actual supplied canonical units. Therefore the output HD label must not be called unsupported/false from the Results paragraph alone. Preserve source statements and independent assessment limits; no image inspection or public dataset validation claimed.',
  variability='Historical byte-identical baseline prompt yielded Xenium24 but omitted femaleVisium3; fresh baseline instead includes femaleVisium3 and omits Xenium24. Temperature0 is not deterministic and one pair cannot establish stable semantic gains.'))
 write(out/'decision.json',dict(scope=__doc__,decision='Retain isolated opt-in representation; DEFER report/production adoption and semantic/generalization claims',
  actual_delta='Same12field bound, same source text/283units/question/criteria/model/output. Candidate allows one observation to list multiple actual requirement_ids, instead of repeating identical study/modality/group/unit/value/unit_id for each criterion. No scientific or source-specific rule, automatic edit or publication gate.',
  fresh_calls=2,field_rows=[12,7],distinct_exact_observation_records=[6,7],duplicated_exact_records=[6,0],
  result='Candidate includes requested Xenium24specimens absent in fresh baseline, while baseline repeats six observations across two criteria. Candidate has no exact duplicate records. These are structural/literal coverage facts, not seven validated facts or an independent correction. Figure1E caption supports the femaleHD attribution that the Results paragraph alone left unclear; no new error is established from this attribute. Independent complete-report retention/new-error assessment remains pending. No complete report revised.',
  legacy_parity='Preserved pre-edit code equals prior immutable executed copy; AST replay reproduces old raw canonical fields parsing exactly; baseline fresh prompt byte-exact historical canonical call01.',
  limitations=['One known paper; eligibility/IF/year ordering/full20-paper selection not resolved.',
   'Requirement associations and omission from unresolved_requirements do not certify whole-criterion completion; source interpretation remains fallible.',
   'Different original groups/datasets/specimens/patients and metadata/own text still need independent semantic checking.',
   'No independent report-level useful retention/new-error assessment or reserved-control validation.'],
  next_work='Assess each source-field observation against complete own-source clauses/captions and original requested units, then test transporting source-specific requested information into a complete original report while preserving useful content and unknown eligibility. Do not discard useful counts merely because other fields remain unknown, and do not infer that a filled or bound field is correct.',independent_correction_credit=0))
 for p in [Path(__file__),Path('local_deep_research/research_verify/canonical_fields.py'),Path('local_deep_research/tests/test_canonical_fields.py'),Path('scripts/run_multi_requirement_if_pair_20261115.py'),Path('scripts/audit_multi_requirement_if_pair_20261115.py')]:
  target=out/'code'/p.resolve().relative_to(Path.cwd());target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 print(json.dumps(dict(handoff=str(out),legacy_parser_parity=True,independent_correction_credit=0)))
if __name__=='__main__':main()
