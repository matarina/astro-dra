"""Preserve neutral original sources/reports separately from fallible candidate opinions."""
import json
from pathlib import Path
from scripts.run_related_report_revision_20261115 import inputs,R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
    cases,groups,_,_,_,_=inputs();a=R/'related-report-revision-model-20261115-v1/attempt';complete=read(a/'completion.json')
    assert complete['status']=='completed_related_report_revision_diagnostic'
    root=R/'related-report-revision-coordinator-handoff-20261115-v1';root.mkdir(exist_ok=False)
    neutral=root/'assessment-input';neutral.mkdir()
    provenance=[]
    for i,c in enumerate(cases):
        folder=neutral/f'case-{i:02d}';folder.mkdir();(folder/'original-question.txt').write_text(c['question'])
        write(folder/'complete-source-units.json',c['units'])
        xml=R/('field-comparison-if-review-packet-20261114-v1/source5-original-article.xml'if i==0 else'acquired-confirmation-coordinator-handoff-20261115-v2/assessment-input/primary-source-9.xml')
        (folder/'primary-source.xml').write_bytes(xml.read_bytes())
        for sid,text,origin in groups[i]:
            assert (a/f'input-report-{sid}.txt').read_text()==text
            (folder/f'report-{sid}.txt').write_text(text)
            provenance.append(dict(artifact_id=sid,origin=origin,report_sha256=sha(folder/f'report-{sid}.txt'),
                status='UNASSESSED',hypothetical_unconfirmed_control=sid in (100002,100003)))
    (neutral/'case-00/candidate-report.txt').write_bytes((a/'candidate-report.txt').read_bytes())
    write(neutral/'status.json',dict(status='UNASSESSED',original_reports=provenance,
        candidate=dict(origin='This isolated source5-only minimal-edit/confirmation pipeline; full IF report, not a new complete20paper research execution',
            model_confirmed_edits=len(complete['revision']['changes']),sha256=sha(a/'candidate-report.txt')),
        independent_scientific_retention_new_error_assessment=False,independent_correction_credit=0))
    write(root/'fallible-readback-answers.json',complete['results']);write(root/'fallible-revision-decisions.json',complete['revision'])
    write(root/'fallible-field-only-questions.json',read(a/'field-only-questions.json'))
    write(root/'execution-evidence.json',dict(audit_manifest_sha256=sha(R/'related-report-revision-terminal-audit-20261115-v1/MANIFEST.json'),
        model_manifest_sha256=sha(a.parent/'MANIFEST.json'),audit=read(R/'related-report-revision-terminal-audit-20261115-v1/audit.json')))
    write(root/'coordinator-findings.json',dict(
        scope='Local report wording and source5-only experimental proposal behavior, not independent scientific adjudication',
        findings=[
            'Question wording input contains question IDs and requested field labels only, no old assertion values. New questions still depend on original target-range navigation for study/method scope; not verified general neutrality.',
            'All five full reports plus target regions and ALL same-citation regions supplied. Original IF sex answer remains allmale; richer hypothesis sex answer remains7male3female. Both fail to expose surviving same-report disagreement despite context availability.',
            'Related-citation enumeration supplies syntactic provenance only; it does not establish scientific scope or make model read every conflict.',
            'All three row-fragment replacements received six true model confirmation booleans, including retention/no-new-error. Actual SeekSpace replacement drops method label, patient1to10 and nuclei-per-section metric; parser appends citation5, so citation presence must not be mistaken for retained content. Final readback admits patientIDs and metric unknown at target. Visium replacement leaves a truncated identifier fragment. These are observable text losses, not independently adjudicated correction credit.',
            'Final candidate length57791 versus original58404, three applied row replacements. Original later SeekSpace allmale prose remains unchanged; model approval did not establish global conflict removal. Candidate is preserved for diagnosis only.',
            'No majority-level correction evidence, complete six-task evaluation,20paper eligibility/IFyear validation, independent retention/new-error clearance or cross-task improvement follows.'
        ],independent_correction_credit=0,
        next_work='Diagnose proposal granularity versus original anchor preservation, and obtain per-occurrence report statements rather than assuming related-region exposure yields a global conflict answer. Keep source adjudication and retention/new-error assessment separate; do not force model approvals or deploy.'))
    for p in [Path(__file__),Path('scripts/run_related_report_revision_20261115.py'),Path('scripts/audit_related_report_revision_20261115.py'),
              Path('local_deep_research/research_verify/retention_inventory.py'),Path('local_deep_research/tests/test_retention_inventory.py')]:
        dest=root/'code'/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    (root/'README.md').write_text('Goal ACTIVE. New independent correction credit0.\n\nNeutral inputs preserve original full questions, primary sources and complete reports. Two prior hypotheses remain explicitly unconfirmed controls; candidate is the actual output of this experimental proposal/confirmation pipeline and has no scientific approval. Model opinions and coordinator findings are outside assessment-input. No independent review requested and no independent-session artifact modified.\n\nAll-citation exposure still failed to report known whole-report disagreement. Proposal scope and retention remain material limits. No deployment, production restart, new Writer/research run or v23 rerun.\n')
    print(json.dumps(dict(path=str(root),manifest_sha256=seal(root),model_confirmed_edits=len(complete['revision']['changes']),independent_correction_credit=0)))

if __name__=='__main__':main()
