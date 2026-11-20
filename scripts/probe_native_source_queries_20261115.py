"""Zero-call replay of existing native source-query options; literal exposure only."""
import json,hashlib,argparse
from pathlib import Path
from scripts.run_source_view_native_pair_20261115 import prepare
from scripts.prepare_source_detail_material_20261114 import native_documents
from research_verify.evidence_flow import _review_material,required_sources,document_structure_spans

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
 case,sources,reports,groups,inputs=prepare();a.out_dir.mkdir(exist_ok=False)
 code=[Path(__file__),Path('scripts/run_source_view_native_pair_20261115.py'),Path('scripts/prepare_source_detail_material_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]
 frozen={str(p):sha(p) for p in [*inputs,*code]};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(frozen,indent=2)+'\n')
 for p in code:
  rel=p.resolve().relative_to(Path.cwd());target=a.out_dir/'code'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
 docs=native_documents(sources);rows=[]
 for arm,gs in groups.items():
  report=reports[arm].read_text();reserve=min(8000,len(json.dumps(document_structure_spans(report),ensure_ascii=False)))
  for number,g in enumerate(gs,1):
   section='\n'.join(c['text'] for c in g.values());needed=required_sources(section,sources)
   for name,scoped,compound in [('default',False,False),('source_scoped',True,False),('source_scoped_compound',True,True)]:
    material,claims=_review_material(docs,case['query']+'\n'+section,g,needed,60000-reserve,source_scoped_question=case['query'] if scoped else None,compound_terms=compound)
    text=str(material);target=a.out_dir/f'{arm}-group{number:02d}-{name}.txt';target.write_text(text)
    rows.append(dict(arm=arm,group=number,variant=name,material_sha256=sha(target),chars=len(text),claim_ids=list(g),source9_Cy7_exposed='Cy7' in text,source3_up_to_exposed='up to 10' in text))
 assert all(sha(Path(p))==h for p,h in frozen.items())
 (a.out_dir/'receipt.json').write_text(json.dumps(dict(scope=__doc__,rows=rows,network_calls=0,model_calls=0,frozen_inputs_unchanged=True,independent_correction_credit=0,prior_adhoc_attempt='v1 was exploratory without a prestart code freeze; v2 freezes and reproduces it. Textual sentinels are evaluator-only and do not enter generation or native code.'),ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(views=len(rows),model_calls=0,source9_candidate_group2=[r for r in rows if r['arm']=='actual_view_scope' and 9 in r['claim_ids']])))
if __name__=='__main__':main()
