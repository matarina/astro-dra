#!/usr/bin/env python3
"""Validate the frozen next-phase run plan without launching duplicate calls.

Use ``run_hallucination_next_phase_experiment_20261113.py`` for the reviewed
isolated fixed-source execution.  This helper remains validation-only.
"""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'evaluation/hallucination-next-phase-20261113'
ap=argparse.ArgumentParser(); ap.add_argument('--validate',action='store_true'); ap.add_argument('--execute',action='store_true'); a=ap.parse_args()
if a.execute: raise SystemExit('use scripts/run_hallucination_next_phase_experiment_20261113.py for the reviewed isolated runner')
plan=json.loads((OUT/'run-plan.json').read_text()); manifest=json.loads((OUT/'manifest.json').read_text())
assert plan['status']=='frozen_before_execution' and manifest['model_calls_in_freeze']==0
assert len(plan['cases'])==5 and [x['id'] for x in plan['arms']]==['baseline','semantic_ranking','evidence_gap','independent_verification']
print(json.dumps({'status':'validated_no_execution','cases':plan['cases'],'arms':[x['id'] for x in plan['arms']],'model_calls':0},indent=2))
