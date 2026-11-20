"""Reject mismatched original inputs before any model invocation."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

RUNNER=Path(__file__).resolve().parents[2]/'scripts/run_hallucination_next_phase_experiment_20261113.py'
spec=importlib.util.spec_from_file_location('original_case_runner',RUNNER)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture_manifest(tmp_path):
    source=tmp_path/'sources.json';source.write_text('[]')
    draft=tmp_path/'original.txt';draft.write_text('Original report [8].')
    query='Original user question'
    row=dict(case_id='original-01',query=query,query_sha256=hashlib.sha256(query.encode()).hexdigest(),
             source=str(source),source_sha256=runner.sha(source),draft=str(draft),draft_sha256=runner.sha(draft))
    path=tmp_path/'manifest.json';path.write_text(json.dumps(dict(cases=[row])))
    return path,row


def test_original_case_accepts_exact_inputs_and_rejects_report_drift(tmp_path):
    path,row=fixture_manifest(tmp_path)
    assert runner._manifest_cases(path)[0]['draft']==Path(row['draft'])
    Path(row['draft']).write_text('Different report [8].')
    with pytest.raises(ValueError,match='input hash mismatch: draft'):runner._manifest_cases(path)


def test_original_case_rejects_question_drift_and_duplicate_namespace(tmp_path):
    path,row=fixture_manifest(tmp_path)
    row['query']='Similar but different question'
    path.write_text(json.dumps(dict(cases=[row])))
    with pytest.raises(ValueError,match='query hash mismatch'):runner._manifest_cases(path)
    row['query_sha256']=hashlib.sha256(row['query'].encode()).hexdigest()
    path.write_text(json.dumps(dict(cases=[row,row])))
    with pytest.raises(ValueError,match='duplicate case_id'):runner._manifest_cases(path)
