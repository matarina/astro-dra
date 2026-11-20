"""Collect frozen-run artifacts and assisted labels without efficacy claims."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
from evidence_eval_metrics import paired


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.root;cfg=json.loads((root/'experiment.json').read_text());sources=json.loads((root/'sources.json').read_text());runs={};trace_checks={}
    for arm in ('baseline','candidate'):
        cases=[];integrity=[]
        for case in cfg['cases']:
            row=json.loads((root/arm/(case['case_id']+'.json')).read_text())
            annpath=root/'assessment'/(arm+'-'+case['case_id']+'.json')
            ann=json.loads(annpath.read_text()) if annpath.exists() else {'status':'annotation_missing'}
            row.update(claims=ann.get('claims',[]),assessment_status=ann['status'],usefulness=ann.get('usefulness'),obligation_assessments=ann.get('obligations',[]))
            cases.append(row)
        for events in (root/arm/'traces').rglob('events.jsonl'):
            rows=[json.loads(line) for line in events.read_text().splitlines()]
            data={};counts=collections.Counter()
            for event in rows:
                counts[event['stage']]+=1
                if event.get('status')=='recorded':
                    raw=gzip.open(events.parent/event['file'],'rb').read()
                    if hashlib.sha256(raw).hexdigest()!=event['sha256']:raise ValueError('Trace hash mismatch')
                    data[event['stage']]=json.loads(raw)
            if 'agent_draft' not in data:continue
            case=next(c for c in cases if c['query']==data['agent_draft']['question'])
            actual=data['input_sources']['sources']
            preserved=len(actual)==len(sources) and all(a.get('abstract')==b.get('abstract') and a.get('pmid')==b.get('pmid') for a,b in zip(actual,sources))
            case['model_calls']=sum(counts[k] for k in ('source_reading_response','writer_response','native_check_response','repair_confirmation_response'))
            # No live retriever in this experiment. Attempted supplements are
            # logged even though the closed fetcher returns no additional data.
            case['tool_calls']=counts['evidence_supplement']
            integrity.append({'case_id':case['case_id'],'sources_preserved':preserved,'native_check_requests':counts['native_check_request'],'supplement_attempts':counts['evidence_supplement'],'stage_counts':dict(counts)})
        trace_checks[arm]=integrity
        runs[arm]={'system':arm,'assessment':{'independence':'separate_blinded_request_same_model_family_not_independent_human','annotation_statuses':dict(collections.Counter(c['assessment_status'] for c in cases))},'cases':cases}
        (root/(arm+'-annotated.json')).write_text(json.dumps(runs[arm],ensure_ascii=False,indent=2))
    result=paired(runs['baseline'],runs['candidate']);result['trace_integrity']=trace_checks
    result['experiment_scope']='nine fixed-source pilot tasks, three task families; no cross-domain control run and no retrieval measurement'
    result['effectiveness']='unproven'
    result['known_biases']=['Assessor shares generator model family.','Only three papers/task families; no representative medical or general-domain sample.','Single generation per arm, temperature zero is not deterministic; order not counterbalanced.','Candidate changes may be inactive on these records.','One common source pool contains all three papers, so task relevance matters independently of citation support.']
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','matched_cases','effectiveness')},indent=2))
    for arm in runs:
        print(arm,json.dumps({k:v for k,v in result[arm].items() if k in ('case_count','claim_count','unsupported_claim_rate','contradicted_claim_rate','citation_entailment_rate','latency_seconds','model_calls')}))


if __name__=='__main__':main()
