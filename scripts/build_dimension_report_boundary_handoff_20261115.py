"""Coordinator evidence only; preserve failed and completed attempts, no independent adjudication."""
from pathlib import Path
import json
from scripts.run_dimension_report_boundary_20261115 import prepare,R,read,write,sha
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.dimension_comparison import hypothetical_report

def main():
    cases,_=prepare();attempt=R/'dimension-report-boundary-model-20261115-v2/attempt'
    completion=read(attempt/'completion.json');assert completion['status']=='completed_dimension_diagnostic'
    edit=read(attempt/'case-00/edit-result.json');assert not edit['changes']
    root=R/'dimension-report-boundary-coordinator-handoff-20261115-v1';root.mkdir(exist_ok=False)
    neutral=root/'assessment-input';neutral.mkdir();proposal=root/'proposal-evidence';proposal.mkdir()
    for i,c in enumerate(cases):
        folder=neutral/f'case-{i:02d}';folder.mkdir();(folder/'original-question.txt').write_text(c['question'])
        (folder/'original-report.txt').write_text(c['report']);(folder/'actual-source-material.txt').write_text(str(c['material']))
        write(folder/'report-provenance.json',dict(scope='Source-targeted full-report experiment under original question; not all-source/task adjudication',
            input_report='Original58404char archive report'if i==0 else'Prior7435char known experimental Writer report, not archive feedback report',
            no_new_retrieval=True,independent_assessment='UNASSESSED'))
    (neutral/'case-00/final-report.txt').write_bytes((attempt/'case-00/candidate-report.txt').read_bytes())
    assert sha(neutral/'case-00/final-report.txt')==sha(neutral/'case-00/original-report.txt')
    for i,path in [(0,R/'field-comparison-if-review-packet-20261114-v1/source5-original-article.xml'),
                   (1,R/'acquired-confirmation-coordinator-handoff-20261115-v2/assessment-input/primary-source-9.xml')]:
        (neutral/f'case-{i:02d}/primary-source.xml').write_bytes(path.read_bytes())
    write(neutral/'assessment-status.json',dict(status='UNASSESSED',actual_IF_final_unchanged=True,immune_comparison_only=True,
        independent_correction_credit=0,no_independent_review_triggered=True))
    write(proposal/'model-proposals-and-decisions.json',edit)
    (proposal/'hypothetical-all-proposals-applied.txt').write_text(hypothetical_report(cases[0]['report'],edit['proposals']['eligible']))
    (proposal/'README.md').write_text('UNCONFIRMED HYPOTHETICAL PROPOSAL, not the final report or a successful correction. Both model-proposed edits were rejected. Retain for source/retention/new-error review; never count as independently corrected output.\n')
    # Literal retention witnesses refute a copying claim, not scientific entailment.
    witnesses=[]
    for index,phrases in [(0,['患者1至10','单细胞空间图谱，面板标题报告每切片的细胞核数（N）']),
                          (1,['用于交叉验证'])]:
        p=edit['proposals']['eligible'][index]
        for phrase in phrases:
            assert phrase in p['addition']
            witnesses.append(dict(candidate_index=index,phrase=phrase,in_model_proposed_replacement=True,
                confirmation_claims_omitted=True,scientific_support='not established merely by literal retention'))
    write(root/'coordinator-findings.json',dict(scope=__doc__,
        failed_v1='Terminalexit2after2returnedstopresponses;5report quote bindings failed. Raw dimensions compared SOURCE with READER instead of REPORT. Preserve frozen v1module/code/rawresponse, do not replay with new parser or call raw output valid.',
        v2='Separate source_supported(SOURCE/READER) from report_dimensions(SOURCE/REPORT), each with source_fact/report_fact. Model selects report anchor IDs, program copies whole actual anchored text/location/hash. Source quotes remain own-source literal bindings. This fixes transport ambiguity, not semantic correctness.',
        statistics=read(R/'dimension-report-boundary-terminal-audit-20261115-v2/audit.json')['statistics'],
        comparison_limits='IFbaseline7present;candidate7partial. Some candidate dimensions call compatible total/subgroup or units differences conflict; taxonomy/scope comprehension unresolved. Immune5presentbotharms: known-source positive-preservation observation, not whole immune task/cell-population coverage or heldout generalization.',
        confirmation_literal_retention_witnesses=witnesses,
        confirmation_real_limit='Repeated SeekSpace10male prose survives both proposed table edits. Preview confirmation correctly notices this, but falsely says three literally retained phrases were lost. Xenium abstract-not-reported qualifier is not automatically a factual contradiction of full-text count; availability scopes must remain distinct.',
        confirmed_applied_edits=0,actual_IF_final_unchanged=True,newly_credited_independent_corrections=0,
        decision='DEFER report/production adoption. No score for abstention or newly structured labels.',
        next_necessary_work='Use independently read before/after fact inventories to test retention judgments separately from overall defect verdicts; distinguish compatible partial coverage from same-scope contradiction. Validate true-retention/true-loss controls grounded in actual source/report edits, then bounded end-to-end matched report/cross-task checks. Do not force approvals using string rules, hide surviving contradictions or repeat prompt-only tweaks as quality gains.',
        independent_adjudication_owner='Other session; no artifact/message or verdict supplied here'))
    write(root/'execution-evidence.json',dict(
        failed_v1_manifest=sha(R/'dimension-report-boundary-model-20261115-v1/MANIFEST.json'),
        failed_v1_audit_manifest=sha(R/'dimension-report-boundary-failed-audit-20261115-v1/MANIFEST.json'),
        completed_v2_manifest=sha(attempt.parent/'MANIFEST.json'),
        completed_v2_audit_manifest=sha(R/'dimension-report-boundary-terminal-audit-20261115-v2/MANIFEST.json'),
        total_fresh_calls=8,total_usage_tokens=515817,independent_correction_credit=0))
    for path in [Path(__file__),Path('scripts/run_dimension_report_boundary_20261115.py'),Path('scripts/audit_dimension_report_boundary_20261115.py'),
                 Path('local_deep_research/research_verify/dimension_comparison.py'),Path('local_deep_research/tests/test_dimension_comparison.py')]:
        target=root/'code'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    (root/'README.md').write_text('Two known-task comparison diagnostic, followed by proposed IF edits and fallible preview confirmation. Whole goal remains ACTIVE; independent new corrections0.\n\nassessment-input contains actual original questions/full reports/supplied source material/primary XML. Actual final IF report is unchanged; immune has comparison only. proposal-evidence is explicitly UNCONFIRMED, not the delivered result. Model opinions/coordinator findings/execution evidence are outside neutral input. No independent review was requested or artifacts overwritten.\n\nV1failed and v2completed are different frozen protocols; no oldattempt overwritten/rerun. V2does not solve semantic assessment: partial-versus-conflict and literal-retention false rejection remain. No production deployment or generic/majority success claim.\n')
    print(json.dumps(dict(path=str(root),manifest_sha256=seal(root),independent_correction_credit=0)))

if __name__=='__main__':main()
