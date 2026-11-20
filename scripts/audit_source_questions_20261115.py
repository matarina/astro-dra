"""Audit the one-call question probe; neutrality still requires semantic review."""
import json
import hashlib
import subprocess
from pathlib import Path
from research_verify.source_questions import inventory,question_prompt,parse_questions
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.isolated_network import assert_network_matches


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    base=Path('evaluation/frontier-strategy-20261113');run=base/'source-questions-model-20261115-v1'
    attempt=run/'attempt';launch=json.loads((run/'launch.json').read_text())
    info=json.loads(subprocess.check_output(['docker','inspect',launch['container_id']]))[0]
    ref=json.loads(subprocess.check_output(['docker','inspect',launch['network_reference_container']]))[0]
    assert info['State']['Status']=='exited' and info['State']['ExitCode']==0
    assert info['Image']==launch['image_id'] and info['Config']['Healthcheck']['Test']==['NONE']
    assert any(m['Destination']=='/workspace'and not m['RW']for m in info['Mounts'])
    assert_network_matches(ref,info)
    count=0
    for file in [run/'launch-freeze.json',attempt/'prestart-freeze.json']:
        for k,v in json.loads(file.read_text()).items():
            assert sha(Path(k.removeprefix('/workspace/')))==v
            count+=1
    case=_manifest_cases(base/'complete-draft-pair-inputs-20261115-v1/case-manifest.json')[0]
    claims=inventory(case['draft'].read_text())
    assert claims==json.loads((attempt/'inventory.json').read_text())
    assert question_prompt(case['query'],claims)==(attempt/'prompt.txt').read_text()
    parsed=parse_questions((attempt/'response.txt').read_text(),claims)
    assert parsed==json.loads((attempt/'questions.json').read_text())
    receipt=json.loads((attempt/'receipt.json').read_text())
    assert receipt['status']=='returned'and receipt['frozen_inputs_unchanged']
    assert receipt['response_metadata']['finish_reason']=='stop'
    audit=dict(status='execution_and_reference_binding_pass',container_id=launch['container_id'],
               frozen_hash_checks=count,model_calls=1,additional_model_calls=0,
               original_claims=len(claims),questions=len(parsed['questions']),
               missing_claims=parsed['claims_without_questions'],unbound_rows=len(parsed['unbound_rows']),
               prompt_sha256=sha(attempt/'prompt.txt'),response_sha256=sha(attempt/'response.txt'),
               token_usage=receipt['response_metadata']['token_usage'],
               neutrality_verified=False,semantic_coverage_verified=False,independent_correction_credit=0)
    out=base/'source-questions-terminal-audit-20261115-v1';out.mkdir(exist_ok=False)
    (out/'terminal-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
