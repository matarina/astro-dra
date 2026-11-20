"""Package completed source-targeted report diagnostic; never write independent review artifacts."""
from pathlib import Path
import json
from scripts.run_associated_field_report_pair_20261115 import prepare,read,sha,write,R
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
    case,original,material,requirements,anchors,jobs,inputs=prepare()
    root=R/'associated-field-report-coordinator-handoff-20261115-v1';root.mkdir(exist_ok=False)
    neutral=root/'assessment-input';neutral.mkdir()
    attempt=R/'associated-field-report-model-20261115-v1/attempt'
    audit=R/'associated-field-report-terminal-audit-20261115-v1'
    assert read(attempt/'completion.json')['frozen_inputs_unchanged']
    (neutral/'original-report.txt').write_text(original)
    (neutral/'original-question.txt').write_text(case['query'])
    (neutral/'acquired-source5.txt').write_text(material.views[5]['text'])
    (neutral/'original-source-pack.json').write_bytes(Path(case['source']).read_bytes())
    xml=R/'field-comparison-if-review-packet-20261114-v1/source5-original-article.xml'
    (neutral/'original-source5-article.xml').write_bytes(xml.read_bytes())
    write(neutral/'canonical-source5-units.json',read(R/'request-canonical-if-model-20261114-v1/attempt/source-units.json'))
    mapping={}
    # Labels carry no arm or coordinator verdict. Original is provided for retention.
    for label,i in [('report-01',1),('report-02',0)]:
        path=attempt/f'arm-{i:02d}/candidate-report.txt';(neutral/f'{label}.txt').write_bytes(path.read_bytes())
        mapping[label]=dict(arm=jobs[i]['arm'],report_sha256=sha(path))
    write(neutral/'assessment-status.json',dict(status='UNASSESSED',scope='Two complete reports from a source5-targeted experiment, plus complete original report, original query and sources. Evaluate proposed changes against primary source, retained useful content, duplicate/remaining contradictions and new errors. Other source claims are unassessed; do not infer full20-paper eligibility/count/IForder or broad correction success.',independent_correction_credit=0))
    write(root/'coordinator-map.json',mapping)
    results=[read(attempt/f'arm-{i:02d}/result.json')for i in range(2)]
    source15=read(neutral/'canonical-source5-units.json')[15]
    assert source15['unit_id']==15 and '7 males and 3 females'in source15['text']
    remaining='SeekSpace空间图谱覆盖10例男性患者'
    assert remaining in original and remaining in (neutral/'report-01.txt').read_text()
    write(root/'coordinator-boundary-findings.json',dict(
        scope='Coordinator diagnosis, NOT independent report correction or outcome scoring',
        source5_result_unit=source15,
        comparison_issue='Both arms label every observation present; a correct total is treated as covering a conflicting sex group, and an abstract-not-reported placeholder as covering a quantity actually available in full text. New/reused cohort detail also collapsed into total counts. Model reasons contradict their labels in places; do not count13present labels as13facts verified.',
        source_to_report_stages=[dict(arm=jobs[i]['arm'],observations=len(results[i]['observations']),comparisons=results[i]['comparisons'],edit_proposals=results[i]['edit_proposals'],decisions=results[i]['decisions'],changes=results[i]['changes'])for i in range(2)],
        repeated_original_statement=remaining,still_in_modified_report=True,
        local_edit='Plural-reading branch replaces one312-character flattened-table anchor with57characters; correct outside-span bytes retained mechanically. It does not revise later conflicting paragraph or Xenium unknown placeholders. It drops patient1-to10 and per-section panel-N wording from chosen row; usefulness/source accuracy of omitted details not independently adjudicated.',
        confirmation_limit='Model approved retains_correct_content and no_new_error despite remaining same-report conflict and broad row replacement. Its statement that requested detail was nowhere else is contradicted by earlier full report passage already stating7male3female. Same model family confirmation is fallible, not independent adjudication.',
        decision='DEFER report/production adoption. Retain generic association adapter as isolated experiment. No scientific quality credit.',
        next_necessary_work='Make comparison express each actual scope/dimension and literal report/source evidence, distinguishing partial overlap, missing detail, contradiction and unknown. Check all occurrences when proposing/confirming edits; use minimal spans that retain table context and requested information. Exercise supported true/false and conflicting/repeated report cases before another bounded original-report experiment. No rule-written corrections or deletion-only fixes.',
        original_20paper_task_complete=False,independent_correction_credit=0))
    write(root/'execution-evidence.json',dict(audit=str(audit),audit_manifest_sha256=sha(audit/'MANIFEST.json'),
        model_manifest_sha256=sha(attempt.parent/'MANIFEST.json'),
        preflight_manifest_sha256=sha(R/'associated-field-report-preflight-20261115-v1/MANIFEST.json'),
        terminal_exit=0,fresh_calls=6,strict_replay_fresh_calls=0,usage=read(audit/'audit.json')['usage'],
        quality_claim=None,independent_correction_credit=0))
    for p in [Path(__file__),Path('scripts/run_associated_field_report_pair_20261115.py'),Path('scripts/audit_associated_field_report_pair_20261115.py'),Path('local_deep_research/research_verify/field_comparison.py'),Path('local_deep_research/tests/test_field_comparison.py')]:
        dest=root/'code'/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    (root/'README.md').write_text('Completed finite source5/full-original-IF-report diagnostic. Independent assessment is UNASSESSED.\n\nassessment-input contains original query/report, two opaque complete outputs, original sourcepack and source5 primary XML/complete acquired text. Coordinator map, model decisions, boundary findings and execution receipts are outside that folder. No independent pane artifact changed or review sent.\n\nOne local model-approved change is not report-level correction: a repeated conflicting statement survives; source-reader completion and all-present comparison labels are not semantic success. Full34/38majority goal remains ACTIVE; new credited independent corrections0.\n')
    print(json.dumps(dict(path=str(root),manifest_sha256=seal(root),independent_correction_credit=0)))

if __name__=='__main__':main()
