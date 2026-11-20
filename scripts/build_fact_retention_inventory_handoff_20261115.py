"""Package span-retention diagnosis; no independent review request or score."""
from pathlib import Path
import json
from scripts.run_fact_retention_inventory_20261115 import prepare,read,write,sha,R
from scripts.audit_associated_field_report_pair_20261115 import seal

def main():
    cases,_,_=prepare();attempt=R/'fact-retention-inventory-model-20261115-v1/attempt'
    complete=read(attempt/'completion.json');assert complete['status']=='completed_retention_diagnostic'
    root=R/'fact-retention-inventory-coordinator-handoff-20261115-v1';root.mkdir(exist_ok=False)
    neutral=root/'assessment-input';neutral.mkdir()
    for i,c in enumerate(cases):
        folder=neutral/f'case-{i:02d}';folder.mkdir()
        write(folder/'input.json',dict(original_question=c['question'],actual_texts=c['texts'],pairs=c['pairs'],complete_source_units=c['units'],
            scope='Span-scoped retention/source/request assessment only. No new complete reports generated. Scientific outcomes UNASSESSED.'))
        (folder/'original-full-report.txt').write_text(c['report'])
        xml=R/('field-comparison-if-review-packet-20261114-v1/source5-original-article.xml'if i==0 else'acquired-confirmation-coordinator-handoff-20261115-v2/assessment-input/primary-source-9.xml')
        (folder/'primary-source.xml').write_bytes(xml.read_bytes())
    write(neutral/'status.json',dict(status='UNASSESSED',no_new_report=True,model_approved_edits=0,independent_correction_credit=0))
    write(root/'model-inventories.json',complete['inventories']);write(root/'model-comparisons.json',complete['results'])
    write(root/'coordinator-provenance-map.json',dict(
        p31='Actual retained SeekSpace table proposal from dimensionv2',p12='Actual retained Xenium table proposal from dimensionv2',
        p76='Actual shorter SeekSpace proposal from associated-field original baseline, drops patient identifiers/panel wording',
        p54='Identity calibration: original actual MACS sentence copied unchanged, not new correction',
        p28='Actual prior adverse native MACS-to-FACS replacement; original and replacement both historical outputs',
        report_origins='IF58404archive original; immune7435known experimental Writer, not original archive feedback output; all known-used diagnostics, not heldout'))
    write(root/'coordinator-findings.json',dict(
        decision='DEFER adoption/automatic approvals. This is a span diagnostic, not full-report improvement.',
        positive_observation='Independent original/candidate inventories and source-scoped comparison now mark patient1to10, panelnucleiN and crossvalidation purpose retained in actual retained proposals, unlike earlier false loss reasons. Immune identity facts retained; actual MACS/Ficoll omission in adverse FACS replacement recognized. No independent quality credit.',
        remaining_failures=[
            'IFp76 originalpatientidentifierfact3 falsely retained although candidate only has count10; model reason explicitly says identifiers not present/omitted, but label stillretained. Count does not establish identity.',
            'IFp31/p76 samplecountfact1=10 labelledsourceconflict/changed by merging neighboring allmalefact2, despite actual source count10. Separate inventory alone does not prevent crossfact contamination.',
            'IFabstract-not-reported assertions labelledconflict from fulltextcount24; abstract and full-text availability scopes not interchangeable.',
            'IF5001panel/286651cells labellednew_requested despite narrow userdesign/groupcount request; request scope not established by source support.',
            'Immune unchanged citation9 token labelledomitted in adverse FACS replacement though token9 remains. Semantic method association changed, but literal token loss claim needs distinction.',
            'Support reasons for report reference numbers rely on article unit text rather than complete report/source identity mapping. Retained citation token is not verified attribution.',
            'Inventories themselves may omit/misparse facts; candidate support labels do not clear qualifiers, whole-report conflicts or new errors.'
        ],
        earlier_whole_report_limit='Proposals leave repeated later SeekSpace10male prose. No full-report repair/adoption happened here; surrounding report absent from modelretentioncalls by design, present only for later review.',
        existing_QA_code_inspected=['research_verify/source_questions.py','research_verify/independent_verification.py','research_verify/questioned_fact_document.py'],
        next_necessary_work='Reuse existing neutral-question/source-only-answer infrastructure for fact-specific before/after answers rather than recreate it. Test count-versus-identity, changed-versus-omitted and abstract/fulltext scope on these actual failures before source-scoped repair integration. No handwritten scientific rules, semantic approvals from lexical tokens or count of model agreement as correction.',
        source_pool_unchanged=True,production_deployment=False,independent_correction_credit=0))
    audit=R/'fact-retention-inventory-terminal-audit-20261115-v1'
    write(root/'execution-evidence.json',dict(audit=str(audit),audit_manifest_sha256=sha(audit/'MANIFEST.json'),
        model_manifest_sha256=sha(attempt.parent/'MANIFEST.json'),fresh_calls=6,usage=read(audit/'audit.json')['usage'],strict_replay_fresh_calls=0,independent_correction_credit=0))
    for p in [Path(__file__),Path('scripts/run_fact_retention_inventory_20261115.py'),Path('scripts/audit_fact_retention_inventory_20261115.py'),
              Path('local_deep_research/research_verify/retention_inventory.py'),Path('local_deep_research/tests/test_retention_inventory.py')]:
        target=root/'code'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    (root/'README.md').write_text('Known-task source-scoped fact-retention diagnostic. No new report/approval/correction score; full goal ACTIVE.\n\nassessment-input contains actual questions/text pairs/full source units/primaryXML and original full reports for later review. Models saw spans/full sources, NOT whole reports. Inventories and model opinions, arm/control provenance and coordinator findings remain outside neutral inputs. No independent review requested or other session artifacts modified.\n\nSeparate inventories improve recognition of three literally retained details but still misclassify count/identity, neighboring facts, availability qualifiers and citation-token retention. Decision DEFER; do not treat zero edits or same-model agreement as semantic improvement of complete reports.\n')
    print(json.dumps(dict(path=str(root),manifest_sha256=seal(root),independent_correction_credit=0)))

if __name__=='__main__':main()
