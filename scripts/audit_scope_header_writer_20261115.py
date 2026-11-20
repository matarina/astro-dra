"""Terminal/cache/header audit only; no semantic scoring or fresh model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.isolated_network import assert_network_matches


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    launch = json.loads((a.run / 'launch.json').read_text())
    inspect = lambda cid: json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
    info, ref = inspect(launch['container_id']), inspect(launch['network_reference_container'])
    assert info['State']['Status'] == 'exited' and info['State']['ExitCode'] == 0
    assert info['Image'] == launch['image_id'] and info['Config']['Healthcheck']['Test'] == ['NONE']
    assert info['Config']['Entrypoint'] == ['/install/.venv/bin/python']
    assert_network_matches(ref, info)
    overlay = lambda obj: sorted((m['Source'], m['Destination'], m['RW']) for m in obj['Mounts'] if m['Destination'].startswith('/install/'))
    assert overlay(info) == overlay(ref) and len(overlay(info)) == 3
    assert all(not m[2] for m in overlay(info))
    assert next(m for m in info['Mounts'] if m['Destination'] == '/workspace')['RW'] is False
    attempt = a.run / 'attempt'
    freeze_counts = {}
    for name, path in [('launch', a.run / 'launch-freeze.json'), ('prestart', attempt / 'prestart-freeze.json')]:
        frozen = json.loads(path.read_text())
        for filename, expected in frozen.items():
            f = Path(filename)
            if f.is_relative_to('/workspace'):
                f = Path.cwd() / f.relative_to('/workspace')
            assert sha(f) == expected, str(f)
        freeze_counts[name] = len(frozen)
    plan = json.loads((attempt / 'plan.json').read_text())
    prior = Path(plan['prior_writer'])
    result = json.loads((attempt / 'result.json').read_text())
    assert result['status'] == 'draft_generated' and result['frozen_inputs_unchanged']
    assert result['origin'] == 'fresh_model'
    assert sha(attempt / 'prompt.txt') == result['prompt_sha256']
    assert sha(attempt / 'response.txt') == result['response_sha256']
    assert sha(attempt / 'candidate-draft.txt') == result['draft_sha256']
    # Replay rechecks canonical article identities, all body hashes, exact
    # reverse header transformation, old baseline and current rendering.
    args = info['Args']
    def flag_value(flag):
        return args[args.index(flag) + 1]
    cmd = [sys.executable, 'scripts/run_scope_header_writer_20261115.py', '--prior-writer', str(prior),
           '--source-views', flag_value('--source-views'), '--bindings', flag_value('--bindings'),
           '--out-dir', str(a.out_dir / 'saved-response-replay'), '--replay-attempt', str(attempt)]
    subprocess.run(cmd, check=True)
    replay = json.loads((a.out_dir / 'saved-response-replay/result.json').read_text())
    assert replay['replay_exact']
    changes = json.loads((attempt / 'changes.json').read_text())
    assert changes == json.loads((a.out_dir / 'saved-response-replay/changes.json').read_text())
    receipt = dict(container_id=launch['container_id'], image=info['Image'], terminal_exit_code=0,
                   frozen_files=freeze_counts, frozen_hashes_unchanged=True,
                   source_bound_headers_changed=len(changes), all_other_prompt_bytes_exact=True,
                   full_nonempty_draft_retained=True, source_texts_reader_notes_fact_registry_unchanged=True,
                   saved_response_replay_exact=True, native_check_executed=False,
                   fresh_model_calls=1, audit_new_model_calls=0, audit_new_retrieval_calls=0,
                   response_metadata=result['response_metadata'], baseline_chars=len((attempt / 'baseline.txt').read_text()),
                   candidate_draft_chars=result['draft_chars'], candidate_draft_sha256=result['draft_sha256'],
                   scientific_quality_assessed=False, independent_correction_credit=0)
    (a.out_dir / 'audit.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
