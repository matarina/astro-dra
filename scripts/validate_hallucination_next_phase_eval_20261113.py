#!/usr/bin/env python3
"""Validate the next-phase freeze without making network/model calls."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'evaluation/hallucination-next-phase-20261113'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fail(m):raise SystemExit('FAIL: '+m)
m=json.loads((OUT/'manifest.json').read_text()); p=json.loads((OUT/'packets/blinded-assessment-packet.json').read_text()); private=json.loads((OUT/'packets/arm-map-private.json').read_text())
if m['model_calls_in_freeze']!=0:fail('freeze includes model calls')
if len(m['historical_cases'])!=3:fail('historical case count')
if len(m['reserved_new_cases'])!=2:fail('new case count')
if m['reserved_identity_check']['overlap_with_existing_evaluation_artifacts']:fail('identity overlap')
if len(p['packets'])!=6:fail('blinded packet count')
ids=[x['blind_id'] for x in p['packets']]
if len(ids)!=len(set(ids)):fail('duplicate blind ids')
if len(private['rows'])!=6 or set(ids)!={x['blind_id'] for x in private['rows']}:fail('private map mismatch')
# Public packet must not contain arm/model/provider fields or arm-bearing source paths.
raw=(OUT/'packets/blinded-assessment-packet.json').read_text().lower()
for token in ['baseline_with_draft','candidate_a_with_draft','candidate_b','arm-map-private','deepseek-v4-flash','source_file']:
 if token in raw:fail('public packet leakage: '+token)
for t in m['reserved_new_cases']:
 if len(t['pmids'])!=3:fail('new task source count')
 for rel in t['source_pack']:
  q=OUT/rel
  if not q.exists():fail('missing source '+str(q))
  d=json.loads(q.read_text())
  if not d.get('pmid') or not d.get('abstract'):fail('incomplete source '+str(q))
print('OK: 3 historical cases, 2 reserved new tasks, 6 blinded packets, no exact PMID overlap, no public arm leakage')
