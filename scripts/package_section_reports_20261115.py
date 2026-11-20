"""Local coordinator-owned assessment inputs/engineering bundle, never sent/scored."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['run','writer-run','audit','case-manifest','diagnosis','assessment','engineering']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();audit=json.loads((a.audit/'audit.json').read_text());assert audit['complete_saved_response_native_replay_exact']
    a.assessment.mkdir(exist_ok=False);a.engineering.mkdir(exist_ok=False);case=json.loads(a.case_manifest.read_text())['cases'][0];mapping={}
    q=a.engineering/'original-question.txt';q.write_text(case['query']+'\n')
    def opaque(src,role,suffix):
        dest=a.assessment/(uuid.uuid4().hex+suffix);shutil.copyfile(src,dest);mapping[dest.name]=dict(role=role,original_path=str(src),sha256=sha(dest))
    opaque(q,'original_question','.txt');opaque(Path(case['draft']),'original_archived_report_not_gold','.txt')
    for arm in ['flat','section']:opaque(a.run/'attempt'/arm/'report.txt',arm+'_complete_report','.txt')
    opaque(Path(case['source']),'same_frozen_generation_sourcepack','.json')
    binding=json.loads((a.case_manifest.parent/'body-bindings.json').read_text())
    for b in binding['bindings']:
        xml=Path(b['xml_path']);assert sha(xml)==b['xml_sha256'];opaque(xml,'primary_xml_source_'+b['source_id'],'.xml')
    readme=a.assessment/(uuid.uuid4().hex+'.md');readme.write_text('Assessment inputs only. The coordinator has not independently adjudicated these reports.\n\nText payloads contain the original question and several complete reports without arm labels; the archived original is not gold. The JSON is the identical generation source pack. Four XMLs are cached primary papers; other source records may have only abstracts or missing text. Acquired views and source identities do not establish complete published-paper access or semantic support.\n\nAssess the original request against original sources: full experimental relationships, attribution and identity, requested methods/platforms/conditions, useful content retained, harmful omissions, unnecessary repetition and newly introduced errors. Distinguish proposals from published methods and abstract silence from whole-paper absence. Headings, tables and summaries require assessment too. Preserve unknown and inaccessible cases. No expected scientific labels, arm mapping, native-check verdicts or coordinator recommendation are included. Shorter reports, valid structures and exact quotations are not quality scores.\n')
    mapping[readme.name]=dict(role='generic_assessment_instructions',original_path=None,sha256=sha(readme));manifest={f.name:sha(f)for f in a.assessment.iterdir()if f.is_file()};write(a.assessment/'MANIFEST.json',manifest);write(a.engineering/'private-assessment-mapping.json',mapping)
    for label,folder in [('writer-run',a.writer_run),('native-run',a.run),('terminal-audit',a.audit),('opaque-assessment',a.assessment)]:shutil.copytree(folder,a.engineering/label)
    prior=Path(json.loads((a.run/'attempt/plan.json').read_text())['prior_attempt']);shutil.copytree(prior,a.engineering/'frozen-prior-attempt')
    shutil.copyfile(a.diagnosis,a.engineering/'coordinator-diagnosis.json')
    for path in ['scripts/run_section_writer_pair_20261115.py','scripts/run_section_native_pair_20261115.py','scripts/audit_section_native_pair_20261115.py',__file__,'local_deep_research/research_verify/section_document.py','local_deep_research/tests/test_section_document.py']:
        src=Path(path);dest=a.engineering/'coordinator-tools'/src.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(src,dest)
    payloads={str(f.relative_to(a.engineering)):sha(f)for f in a.engineering.rglob('*')if f.is_file()};write(a.engineering/'MANIFEST.json',payloads)
    assert all(sha(a.engineering/k)==h for k,h in payloads.items())and all(sha(a.assessment/k)==h for k,h in manifest.items())
    receipt=dict(assessment_payloads=len(manifest),engineering_payloads=len(payloads),all_payload_hashes_verified=True,engineering_manifest_sha256=sha(a.engineering/'MANIFEST.json'),assessment_manifest_sha256=sha(a.assessment/'MANIFEST.json'),reviewer_owned_files_written=0,messages_sent=0,independent_assessment_received=False,new_independent_correction_credit=0)
    write(a.engineering.parent/(a.engineering.name+'-receipt.json'),receipt);print(json.dumps(receipt))


if __name__=='__main__':main()
