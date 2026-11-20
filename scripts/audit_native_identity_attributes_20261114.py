"""Read-only terminal/integrity audit of the finite native-prompt comparison."""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from research_verify.claims import extract_report_claims
from research_verify.citation_display import cited_indices


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True);a=ap.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=False)
    plan=json.loads((a.attempt/'plan.json').read_text());calls=json.loads((a.attempt/'calls.json').read_text())
    completion=json.loads((a.attempt/'completion.json').read_text())
    handle=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',handle['container']],text=True))[0]
    assert state['Id']==handle['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    assert completion['calls']==len(calls)==2*len(plan['jobs'])==12
    assert completion['frozen_inputs_unchanged'] is True
    freeze=json.loads((a.attempt/'prestart-freeze.json').read_text())
    snapshots={}
    root=Path.cwd()
    for name,digest in freeze.items():
        p=Path(name)
        rel=p.relative_to('/workspace') if p.is_relative_to('/workspace') else (p.relative_to(root) if p.is_absolute() else p)
        saved=a.attempt/'code'/rel
        if saved.exists():assert sha(saved)==digest;snapshots[name]=digest
        else:assert sha(root/rel)==digest
    rows=[];identities={'authors','journal','publication_year','publication_type','publication_state','language','journal_metric'}
    for job in plan['jobs']:
        folder=a.attempt/job['name'];assert sha(folder/'material.txt')==job['material_sha256']
        if job.get('only_appended_identity_instructions'):
            assert (folder/'identity_attributes-prompt.txt').read_text().startswith((folder/'control-prompt.txt').read_text()+'\n\n')
        else:
            assert job.get('annotated_claims')
            for key,claim in job['annotated_claims'].items():
                assert claim['text']==job['claims'][key]['text']
                for span in claim['literal_assertion_spans']:
                    assert claim['text'][span['start']:span['end']]==span['text']
                    assert span['explicit_source_ids']==sorted(cited_indices(span['text']))
        for arm,digest in job['prompt_hashes'].items():
            assert sha(folder/(arm+'-prompt.txt'))==digest
            c=next(x for x in calls if x['name']==job['name'] and x['arm']==arm)
            response=folder/(arm+'-response.txt')
            if c.get('response_sha256'):assert sha(response)==c['response_sha256']
            atoms=[atom for issue in c.get('issues',[])+c.get('checked',[]) for atom in issue.get('atom_checks',[])]
            counts=Counter(atom.get('attribute_role',atom.get('attribute')) for atom in atoms)
            rows.append(dict(name=job['name'],arm=arm,status=c['status'],response_sha256=sha(response) if response.exists() else None,
                             explicit_identity_roles={k:v for k,v in counts.items() if k in identities},
                             atom_roles=dict(counts)))
    # A literal, reproducible missed-coverage example; NOT a source-truth verdict.
    job=next(j for j in plan['jobs'] if j['name']=='report-04-group-000')
    claim=job['claims']['5'];text=claim['text']
    spans=[dict(text=c.text,start=c.report_start,end=c.report_end,explicit_citations=list(c.citations)) for c in extract_report_claims(text)]
    assert all(text[s['start']:s['end']]==s['text'] for s in spans)
    material=(a.attempt/job['name']/'material.txt').read_text()
    at=material.index('[8]\nTitle:');header=material[at:material.index('Abstract:',at)] if 'Abstract:' in material[at:] else material[at:at+1200]
    assert 'Journal: Cells\n' in header and any(s['explicit_citations']==[8] and 'Pharmacological Research' in s['text'] for s in spans)
    (a.out_dir/'merged-unit-example.json').write_text(json.dumps(dict(parent_claim=claim,literal_assertions=spans,
        supplied_source_header=header,scope='Text exposure and model coverage diagnosis; not independent source adjudication'),ensure_ascii=False,indent=2)+'\n')
    audit=dict(container=dict(id=state['Id'],image=state['Image'],status=state['State']['Status'],exit_code=state['State']['ExitCode']),
               calls=len(calls),parsed=sum(r['status']=='parsed' for r in rows),unavailable=sum(r['status']!='parsed' for r in rows),
               completion_frozen_inputs_unchanged=True,verified_code_snapshots=snapshots,
               frozen_noncode_inputs_verified=True,rows=rows,quality_claim=None,newly_credited_corrections=0,
               limits=['Model labels and explicit atom counts are not independent correctness or retention evidence.',
                       'Only six preselected native groups, two report families; no full report was generated or corrected.',
                       'Whole-unit supported labels do not certify coverage of every asserted field.'])
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(calls=audit['calls'],parsed=audit['parsed'],unavailable=audit['unavailable'],newly_credited_corrections=0)))


if __name__=='__main__':main()
