"""Coordinator-only complete-report readback evidence, no scientific adjudication."""
from pathlib import Path
import json
from scripts.run_fact_question_readback_20261115 import prepare,navigation_regions,read,write,sha,R
from scripts.audit_associated_field_report_pair_20261115 import seal
from research_verify.request_fields import original_anchors

def main():
    cases,_,groups,_=prepare();root=R/'fact-question-readback-coordinator-handoff-20261115-v1';root.mkdir(exist_ok=False)
    neutral=root/'assessment-input';neutral.mkdir()
    a1=R/'fact-question-readback-model-20261115-v1/attempt';a2=R/'fact-question-readback-model-20261115-v2/attempt'
    for i,c in enumerate(cases):
        folder=neutral/f'case-{i:02d}';folder.mkdir();(folder/'original-question.txt').write_text(c['question'])
        write(folder/'complete-source-units.json',c['units'])
        xml=R/('field-comparison-if-review-packet-20261114-v1/source5-original-article.xml'if i==0 else'acquired-confirmation-coordinator-handoff-20261115-v2/assessment-input/primary-source-9.xml')
        (folder/'primary-source.xml').write_bytes(xml.read_bytes())
        for sid,text,origin in groups[i]:
            assert (a1/f'report-{sid}.txt').read_text()==(a2/f'report-{sid}.txt').read_text()==text
            (folder/f'report-{sid}.txt').write_text(text)
    write(neutral/'artifact-provenance.json',read(a2/'coordinator-artifact-map.json'))
    write(neutral/'status.json',dict(status='UNASSESSED',scope='Five known/hypothetical complete reports used for text-only readback. Scientific support/retention/new errors not adjudicated; hypothetical reports are NOT approved/research pipeline outputs.',independent_correction_credit=0))
    results1=read(a1/'completion.json')['results'];results2=read(a2/'completion.json')['results']
    write(root/'readback-v1.json',results1);write(root/'readback-v2.json',results2);write(root/'fallible-question-plans.json',read(a1/'question-plans.json'))
    neighborhoods=[]
    for i,group in enumerate(groups):
        for sid,text,origin in group:
            # Syntactic citation neighborhoods only; no scientific keyword filter.
            anchors=original_anchors(text);source_ids=cases[i]['source_ids']
            neighborhoods.append(dict(artifact_id=sid,citation_source_ids=sorted(source_ids),
                directly_cited_regions=[a for a in anchors if set(a['citation_ids'])&source_ids]))
    write(root/'coordinator-related-citation-regions.json',neighborhoods)
    write(root/'coordinator-findings.json',dict(
        scope='Report-wording diagnostic only; all verification statuses refer to text presence, not primary truth',
        v1_failure='9IFquestions discard method/study scope and answer different cervicalpaper/source1 instead of intended breastpaper/source5. Questions about10samples embed old count;2IForiginalitems uncovered after duplicate generic questions. Immune4questions still assumeCCR3positive target. These are adapter/planning diagnostics, not proof a production verifier has same routing.',
        v2_change='Reuse exact9IF/4immune fallible questions; add actual target report ranges with hashes projected through existing declared hypothetical edits/native replacement. All five full report bytes identical between protocols; no source subtraction or new fact/answer from outside this report.',
        v2_local_observation='Original/richerIF report supplies patient1to10; shorterhypothesis patientIDanswerunknown despite count10. Full report readback distinguishes samplecount from identifier locally. Originalimmune answersMACS/antiCy7/Ficoll; actualnative report answersFACS/no beads and unknownFicoll.',
        limits=[
            'No source scientific support follows from a report-supported status. No report generation, approvals or actual corrections in this experiment.',
            'Same known questions and model family; protocol/run variation and added navigation do not prove stable isolated improvement or generalization.',
            'V2originalSeekSpace answersallmale, whereas earlier same-report passage states7male3female. Richerhypothesis answers7male3female but later10male prose survives. Global same-paper conflict remains undetected despite complete report availability.',
            'Navigation can anchor answers to one location and obscure same-study counterevidence. Complete-context presence alone is insufficient.',
            'Planner omitted2IFitems and leaks10samples in sex/identifier questions; no verified neutrality/coverage. Generic platform/citationquestions collapse distinct modalities.',
            'Some generated reportquotes remainunlocated; effective unknowns stay visible. Nativequestion jointlyaskingantibodiesandbeads can be labelledsupported while answer says beadsnotreported.',
            'Candidate new scientific claims and task eligibility/20papers/IFordering not independently cleared by original-fact questions.'
        ],
        decision='Retain isolated namespace/range-binding adapter; DEFER scientific report adoption and semantic success claim.',
        next_necessary_work='Use actual citation-linked same-study report occurrences as navigation counterevidence alongside target spans, and repair question scope without embedding old values. Existing same-source citation neighborhood index preserved here is syntactic provenance, not proof every region has same semantic scope. Then test whole-report conflicts and connect source-grounded correction/useful-retention/new-error validation across tasks. Do not force approvals from local matching answers.',
        independent_correction_credit=0))
    audit1=R/'fact-question-readback-terminal-audit-20261115-v1';audit2=R/'fact-question-readback-terminal-audit-20261115-v2'
    write(root/'execution-evidence.json',dict(v1_audit_manifest=sha(audit1/'MANIFEST.json'),v2_audit_manifest=sha(audit2/'MANIFEST.json'),
        v1_model_manifest=sha(a1.parent/'MANIFEST.json'),v2_model_manifest=sha(a2.parent/'MANIFEST.json'),
        total_fresh_calls=12,total_tokens=163202,strict_replay_fresh_calls=0,report_changes=0,independent_correction_credit=0))
    for p in [Path(__file__),Path('scripts/run_fact_question_readback_20261115.py'),Path('scripts/audit_fact_question_readback_20261115.py'),
              Path('local_deep_research/research_verify/retention_inventory.py'),Path('local_deep_research/tests/test_retention_inventory.py')]:
        target=root/'code'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    (root/'README.md').write_text('Complete-report QUESTION READBACK, not primary-scientific verification. Goal ACTIVE; new credited independent corrections0.\n\nassessment-input contains original full questions, primary source units/XML for future review and all five complete report artifacts. Provenance labels distinguish actual historical outputs from UNCONFIRMED hypothetical proposal controls. No new research output or approved report was produced.\n\nV1lost study scope; v2adds current-report bound navigation while keeping same questions/report bytes. Local count/identifier and MACS/Ficoll readback improves; whole-report conflicts, vague/leaking questions and unlocated quotations remain. Model answers/opinions and coordinator findings are outside neutral inputs. No independent review requested or other session artifacts modified.\n')
    print(json.dumps(dict(path=str(root),manifest_sha256=seal(root),independent_correction_credit=0)))

if __name__=='__main__':main()
