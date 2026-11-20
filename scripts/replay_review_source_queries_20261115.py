"""Four offline retrieval arms on complete matched native report groups.

Controls are evaluator-only literal original paragraphs, never retrieval input.
No source semantic labels, model calls, report edits or majority scoring.
"""
import argparse,hashlib,json
from pathlib import Path
from research_verify.evidence_flow import _review_material,review_claim_groups,document_structure_spans,required_sources
from scripts.prepare_source_detail_material_20261114 import native_documents


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113');attempt=base/'complete-draft-pair-model-20261115-v1/attempt';plan=json.loads((attempt/'plan.json').read_text());question=plan['query'];controls_path=base/'fragment-revision-retention-controls-20261114-v2.json';controls=json.loads(controls_path.read_text())['source_units'];rows=[];inputs={str(attempt/'plan.json'):sha(attempt/'plan.json'),str(controls_path):sha(controls_path)}
    for report_arm in ['inherited','fresh']:
        result_path=attempt/report_arm/'result.json';report_path=attempt/report_arm/'report.txt';inputs.update({str(p):sha(p)for p in [result_path,report_path]});sources=json.loads(result_path.read_text())['sources'];report=report_path.read_text();docs=native_documents(sources);groups=review_claim_groups(report,docs,sources,question,60000);reserve=min(8000,len(json.dumps(document_structure_spans(report),ensure_ascii=False)));trace=[json.loads(line)for line in (attempt/report_arm/'trace.jsonl').read_text().splitlines()];requests=[e['data']for e in trace if e['stage']=='native_check_request'and e['data']['round']==1];assert len(requests)==len(groups)
        for index,claims in enumerate(groups,1):
            section='\n'.join(c['text']for c in claims.values());query=question+'\n'+section;required=required_sources(section,sources)
            for name,scoped,compound in [('legacy',False,False),('compounds',False,True),('source_queries',True,False),('combined',True,True)]:
                material,shown_claims=_review_material(docs,query,claims,required,60000-reserve,source_scoped_question=question if scoped else None,compound_terms=compound)
                assert shown_claims==claims
                folder=a.out_dir/report_arm/f'group-{index:02d}'/name;folder.mkdir(parents=True)
                path=folder/'material.txt';path.write_text(str(material));(folder/'views.json').write_text(json.dumps(material.views,ensure_ascii=False,indent=2)+'\n')
                if name=='legacy':
                    expected=requests[index-1]['prompt'].split('SUPPLIED SOURCES:\n',1)[1].split('\n\nSTRUCTURAL REPORT SPANS',1)[0];assert str(material)==expected,(report_arm,index)
                rows.append(dict(report_arm=report_arm,group=index,mode=name,source_ids=sorted(material.views),material_chars=len(material),material_sha256=sha(path),compound_terms=compound,source_scoped_queries=scoped,default_matches_saved_prompt=name=='legacy',control_paragraphs=[dict(source_id=u['source_id'],source_in_group=u['source_id']in material.views,complete_text_present=u['text']in str(material))for u in controls]))
    files={str(p):sha(p)for p in [Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),Path('local_deep_research/overlay/base_citation_handler.py'),*Path('local_deep_research/research_verify').glob('*.py')]};receipt=dict(scope='Offline retrieval boundary comparison on two outputs of SAME known task, not independent science/generalization',inputs=inputs,code_hashes=files,rows=rows,default_all_six_initial_native_materials_byte_identical=True,model_calls=0,network_reads=0,report_modifications=0,new_independently_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(default_materials_identical=True,rows=rows,model_calls=0),ensure_ascii=False))


if __name__=='__main__':main()
