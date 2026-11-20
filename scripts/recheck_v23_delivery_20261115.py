"""Read-only rehash of completed v23 outputs and trace payloads. No evaluation/model calls."""
import gzip, hashlib, json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=Path('evaluation/frontier-strategy-20261113');ap=r/'terminal-v23-production-packet-bundles-writer-audit-v1.json';a=json.loads(ap.read_text())
fp=r/'matched-production-packet-immune-bundles-v23-20261114T130000Z-prestart-hash-freeze.json';f=json.loads(fp.read_text());assert sha(fp)==a['hash_freeze']['sha256']
run=Path(a['run_path']);sp=run/'summary.json';s=json.loads(sp.read_text());assert sha(sp)==a['summary_sha256']
hashes={};arms={};traces=[]
for name in ['baseline','evidence_gap']:
 d=json.loads((run/'historical-immune'/name/'result.json').read_text())
 for fn,record in a['arms'][name]['files'].items():
  path=Path(record['path']);assert sha(path)==record['sha256'];hashes[str(path)]=sha(path)
 p=run/'historical-immune'/name/'report.md';calls=json.loads((p.parent/'calls.json').read_text())
 assert sha(p)==d['report_sha256'] and len(p.read_text())==d['report_chars']
 assert len(calls)==d['model_calls']
 assert all(d['protocol']['code_sha256'][k]==v for k,v in f['code_sha256'].items())
 arms[name]={'calls':len(calls),'chars':len(p.read_text()),'report_sha256':sha(p),'status':d['status']}
for trace in a['writer_traces']:
 p=Path(trace['index_path']);assert sha(p)==trace['index_sha256'];n=0
 for e in trace['events']:
  if e.get('status')=='recorded' and e.get('file'):
   raw=gzip.decompress((p.parent/e['file']).read_bytes());assert hashlib.sha256(raw).hexdigest()==e['sha256'];n+=1
 traces.append({'index':str(p),'sha256':sha(p),'rehash_payload_count':n})
assert all(s['protocol']['code_sha256'][k]==v for k,v in f['code_sha256'].items())
for p,h in f['input_sha256'].items():assert sha(Path(p))==h
candidate=json.loads((run/'historical-immune/evidence_gap/result.json').read_text());receipts=candidate['candidate_attachment_receipts'];cards=[c for batch in receipts for receipt in batch['candidate_attachment_receipts'] for c in receipt['cards']]
from collections import Counter
print(json.dumps({'scope':__doc__,'audit_sha256':sha(ap),'freeze_sha256':sha(fp),'summary_sha256':sha(sp),'arms':arms,
 'three_code_hashes_match_startup_protocol_and_arm_completion_records':True,
 'current_workspace_code_hash_not_expected_to_equal_old_code':True,
 'trace_indexes':traces,'rehash_files':hashes,'format_receipt_status_counts':dict(Counter(c['status'] for c in cards)),
 'independent_correction_credit':0,'semantic_quality_claim':None},ensure_ascii=False,indent=2))
