"""Stage complete matched report and original evidence for external independent review."""
import argparse,hashlib,json,shutil
from pathlib import Path
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-manifest',type=Path,required=True);p.add_argument('--attempt',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    audit=json.loads(a.audit.read_text());assert audit['exit_code']==0 and audit['complete_native_and_sequential_replay']
    complete=json.loads((a.attempt/'completion.json').read_text());assert complete['frozen_inputs_unchanged']is True
    case=_manifest_cases(a.case_manifest)[0]
    a.out_dir.mkdir(parents=True,exist_ok=False);packet=a.out_dir/'independent-review-inputs';packet.mkdir()
    (packet/'request.txt').write_text(case['query'])
    shutil.copyfile(a.attempt/'original-report.txt',packet/'report-original.txt')
    shutil.copyfile(a.attempt/'candidate/report.txt',packet/'report-Q7.txt')
    assert sha(packet/'report-original.txt')==json.loads((a.attempt/'plan.json').read_text())['original_report_sha256']
    assert sha(packet/'report-Q7.txt')==complete['candidate']['report_sha256']
    shutil.copyfile(a.attempt/'final-source-records.json',packet/'sources-original-namespace.json')
    primary=packet/'primary-evidence';primary.mkdir();events=[]
    for event in complete['primary_transport']:
        if event.get('status')=='retrieved':
            file=event.get('file')or f"primary-response-{event['index']:03d}.txt"
            assert Path(file).name==file
            assert sha(a.attempt/file)==event['sha256'];shutil.copyfile(a.attempt/file,primary/file)
    for event in complete['primary_acquisitions']:
        item=dict(source_index=event['source_index'],status=event['status'])
        if event['status']=='acquired':
            file=event['file'];assert sha(a.attempt/file)==event['sha256'];shutil.copyfile(a.attempt/file,primary/file);item.update(file=file,sha256=event['sha256'])
        events.append(item)
    (packet/'primary-provenance.json').write_text(json.dumps(dict(transport=complete['primary_transport'],articles=events),ensure_ascii=False,indent=2)+'\n')
    scope=dict(scope='Complete archived report after isolated post-writer review; not new retrieval/writing or a six-task outcome result',case_id=case['case_id'],
        requested_review='Independently inspect original and report-Q7 against original primary sources. Assess factual and bibliographic changes, requested useful content retained, source/date/language eligibility, and newly introduced errors. Missing/uncertain evidence remains unresolved. Return exact source/report spans and primary-source identities for every judgement.',
        source_timing='Metadata/abstracts and new original-source article text acquired after historical report. They do not establish historical writer exposure.',
        source_limits='Many sources have abstract/metadata only or no bound record. New article extraction and raw responses are supplied where actually obtained; absence of retrieved evidence does not prove paper absence.',
        locator_limits='An archived URL and matching response hash establish locator provenance only. A retrieved document may be a review or nonresearch page; stable paper identity, original-study status and request eligibility require independent assessment. No metadata promotion is implied.',
        model_scope='Model replies and engineering success labels are intentionally excluded; they are not adjudication evidence.',
        review_status='Staged only; no independent reviewer contacted, no verdict or outcome score supplied.',
        frozen_global_scope=dict(tasks=6,primary_allegations=34,stress_units=38,strict_majority_primary=18,strict_majority_stress=20),
        correction_credit='Only independently adjudicated matched-report corrections with retained usefulness/new-error checks may be counted; this packet assigns no credit.')
    (packet/'scope.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2)+'\n')
    manifest={str(f.relative_to(packet)):dict(sha256=sha(f),bytes=f.stat().st_size)for f in sorted(packet.rglob('*'))if f.is_file()}
    (packet/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    assert all(sha(packet/n)==r['sha256']and (packet/n).stat().st_size==r['bytes']for n,r in manifest.items())
    provenance=dict(attempt=str(a.attempt),audit=str(a.audit),audit_sha256=sha(a.audit),packet_files=len(manifest),independent_review_status='not_assessed',newly_credited_corrections=0)
    (a.out_dir/'private-staging-receipt.json').write_text(json.dumps(provenance,indent=2)+'\n');(a.out_dir/'staging-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(packet_files=len(manifest),independent_review_status='not_assessed',newly_credited_corrections=0)))


if __name__=='__main__':main()
