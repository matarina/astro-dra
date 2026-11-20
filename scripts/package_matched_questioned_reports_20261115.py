"""Create coordinator-owned opaque assessment inputs and hashed engineering copy.

Does not send, publish, score, adjudicate, or touch reviewer-owned artifacts.
"""
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
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--assessment',type=Path,required=True)
    p.add_argument('--engineering',type=Path,required=True)
    p.add_argument('--diagnosis',type=Path,required=True)
    a=p.parse_args()
    audit=json.loads((a.audit/'audit.json').read_text())
    assert audit['complete_saved_response_native_replay_exact']
    c=json.loads((a.run/'attempt/completion.json').read_text())
    assert all(r['status']=='completed'for r in c['arms'])and c['frozen_inputs_unchanged']
    a.assessment.mkdir(exist_ok=False);a.engineering.mkdir(exist_ok=False)
    case=json.loads((a.inputs/'case-manifest.json').read_text())['cases'][0]
    mapping={}
    def opaque(src,role,suffix):
        name=uuid.uuid4().hex+suffix;dest=a.assessment/name
        shutil.copyfile(src,dest);mapping[name]=dict(role=role,original_path=str(src),sha256=sha(dest))
    q=a.engineering/'question.txt';q.write_text(case['query']+'\n');opaque(q,'original_question','.txt')
    opaque(Path(case['draft']),'original_archived_report_not_gold','.txt')
    for arm in ['baseline','candidate']:opaque(a.run/'attempt'/arm/'report.txt',f'{arm}_complete_report','.txt')
    opaque(a.inputs/'sources.json','same_frozen_generation_source_pack','.json')
    bindings=json.loads((a.inputs/'body-bindings.json').read_text())
    for b in bindings['bindings']:opaque(Path(b['xml_path']),f"cached_primary_xml_source_{b['source_id']}",'.xml')
    readme=a.assessment/(uuid.uuid4().hex+'.md')
    readme.write_text('Assessment input only; coordinator has not independently adjudicated these reports.\n\nThe text payloads contain the original question and several complete reports without arm labels. The archived original is not gold. The JSON payload is the same generation source pack. Four XML payloads are cached primary papers; other records may have only abstracts or missing text. Source identifiers and acquired text do not establish semantic support or whole-paper completeness.\n\nAssess against original primary sources: full relationships, attribution and identity, requested fields, omissions and duplicates, useful supported content retained, and newly introduced errors. Preserve uncertain and inaccessible cases. Distinguish source-backed correction from omission, rewritten wording, model agreement and execution success. Do not infer success or quality from longer reports or additional facts. No expected scientific labels or coordinator recommendation are included.\n')
    mapping[readme.name]=dict(role='generic_assessment_instructions',original_path=None,sha256=sha(readme))
    manifest={f.name:sha(f)for f in a.assessment.iterdir()if f.is_file()}
    write(a.assessment/'MANIFEST.json',manifest)
    write(a.engineering/'private-assessment-mapping.json',mapping)
    shutil.copyfile(a.diagnosis,a.engineering/'coordinator-boundary-diagnosis.json')
    for label,folder in [('run',a.run),('inputs',a.inputs),('terminal-audit',a.audit),('assessment',a.assessment)]:
        shutil.copytree(folder,a.engineering/label)
    for f in ['scripts/run_matched_questioned_reports_20261115.py','scripts/audit_matched_questioned_reports_20261115.py',__file__]:
        dest=a.engineering/'coordinator-tools'/Path(f).name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(f,dest)
    payloads={str(f.relative_to(a.engineering)):sha(f)for f in a.engineering.rglob('*')if f.is_file()}
    write(a.engineering/'MANIFEST.json',payloads)
    assert all(sha(a.engineering/k)==h for k,h in payloads.items())
    assert all(sha(a.assessment/k)==h for k,h in manifest.items())
    receipt=dict(assessment_payloads=len(manifest),engineering_payloads=len(payloads),all_payload_hashes_verified=True,assessment_manifest_sha256=sha(a.assessment/'MANIFEST.json'),engineering_manifest_sha256=sha(a.engineering/'MANIFEST.json'),reviewer_owned_files_written=0,messages_sent=0,independent_assessment_received=False,new_independent_correction_credit=0)
    write(a.engineering.parent/(a.engineering.name+'-receipt.json'),receipt)
    print(json.dumps(receipt))


if __name__=='__main__':main()
