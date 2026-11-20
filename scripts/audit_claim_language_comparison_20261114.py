"""Check paired language presentation and response integrity, not semantic gold."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from research_verify.claim_language import parse_translations,translation_prompt
from research_verify.source_fact_review import CONCEPT_COMPARISON_INSTRUCTIONS
from scripts.run_claim_language_comparison_20261114 import PRESENTATION_NOTE


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    h=json.loads((a.attempt.parent/'execution-handle.json').read_text())
    state=json.loads(subprocess.check_output(['docker','inspect',h['container']],text=True))[0]
    assert state['Id']==h['container_id'] and state['State']['Status']=='exited' and state['State']['ExitCode']==0
    c=json.loads((a.attempt/'completion.json').read_text());assert c['frozen_inputs_unchanged'] is True
    plan=json.loads((a.attempt/'plan.json').read_text());freeze=json.loads((a.attempt/'prestart-freeze.json').read_text());root=Path.cwd()
    for name,digest in freeze.items():
        path=Path(name);rel=path.relative_to('/workspace') if path.is_relative_to('/workspace') else (path.relative_to(root) if path.is_absolute() else path)
        snapshot=a.attempt/'code'/rel;assert sha(snapshot if snapshot.exists() else root/rel)==digest
    launch=json.loads((a.attempt.parent/'launch-code-freeze.json').read_text())
    assert all(freeze.get('/workspace/'+n,freeze.get(n))==h for n,h in launch.items())
    calls=json.loads((a.attempt/'calls.json').read_text());assert len(calls)==c['calls']==6
    for call in calls:
        path=a.attempt/call['job']/f"call-{call['call_id']:03d}-prompt.txt";assert sha(path)==call['prompt_sha256']
        assert call['status']=='returned' and sha(path.with_name(path.name.replace('-prompt','-response')))==call['response_sha256']
    rows=[]
    for job in plan['jobs']:
        folder=a.attempt/job['name'];claims={int(k):v for k,v in job['claims'].items()}
        selected=[call for call in calls if call['job']==job['name']]
        translation=next(x for x in selected if x['stage']=='translation')
        assert (folder/f"call-{translation['call_id']:03d}-prompt.txt").read_text()==translation_prompt(claims)
        translated=parse_translations((folder/f"call-{translation['call_id']:03d}-response.txt").read_text(),claims)
        original_call=next(x for x in selected if x['stage']=='original_native_check');english_call=next(x for x in selected if x['stage']=='english_native_check')
        original=(folder/f"call-{original_call['call_id']:03d}-prompt.txt").read_text();english=(folder/f"call-{english_call['call_id']:03d}-prompt.txt").read_text()
        suffix='\n\n'+CONCEPT_COMPARISON_INSTRUCTIONS+'\n\n'+PRESENTATION_NOTE
        assert original==(folder/'base-native-prompt.txt').read_text()+suffix
        assert original.split('\nFINAL ANSWER:\n',1)[0]==english.split('\nFINAL ANSWER:\n',1)[0]
        assert original.split('\n\nSUPPLIED SOURCES:',1)[1]==english.split('\n\nSUPPLIED SOURCES:',1)[1]
        opayload=json.loads(original.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
        epayload=json.loads(english.split('\nFINAL ANSWER:\n',1)[1].split('\n\nSUPPLIED SOURCES:',1)[0])
        assert len(opayload)==len(epayload)==len(claims)
        for before,after in zip(opayload,epayload):
            assert {k:v for k,v in before.items() if k not in {'text','literal_assertion_spans'}}=={k:v for k,v in after.items() if k not in {'text','literal_assertion_spans'}}
            assert after['text']==translated[before['claim_id']]['text']
        results=[x for x in c['results'] if x['job']==job['name']]
        rows.append(dict(job=job['name'],claims=len(claims),translation_complete_syntax=True,unchanged_source_and_context_bytes=True,
            translated_units=translated,checks=[dict(arm=x['arm'],status=x['status'],issues=x.get('issues',[]),checked=x.get('checked',[])) for x in results]))
    a.out_dir.mkdir(parents=True,exist_ok=False)
    audit=dict(scope='Source-blind translation and source/context byte matching only; no independent translation fidelity or correction score',
        exit_code=state['State']['ExitCode'],verified_launch_startup_completion_hashes=True,calls=len(calls),rows=rows,
        report_changes=False,quality_claim=None,newly_credited_corrections=0,
        limits=['Citation/ID preservation does not prove translation fidelity.',
                'Translated literal sentence annotations differ with language; this is a presentation intervention.',
                'Only two previously exposed groups; no held-out or full six-task outcome.',
                'No original-language report revision or independent correction/retention/new-error assessment.'])
    (a.out_dir/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (a.out_dir/'audit-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(calls=len(calls),rows=len(rows),report_changes=False,newly_credited_corrections=0)))


if __name__=='__main__':main()
