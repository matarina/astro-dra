"""Read-only identifier crosswalk; does not score or transfer feedback labels."""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.bibliography_identity import bibliography_entries,match_identifiers


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=False)
    primary_path=Path('evaluation/pane2-independent-review-20261113/nonimmune-primary-evidence.json')
    primary=json.loads(primary_path.read_text())['records']
    primary_records={k:r['metadata'] for k,r in primary.items() if isinstance(r.get('metadata'),dict)}
    readiness_path=Path('evaluation/frontier-strategy-20261113/six-task-input-readiness-20261114-v1.json')
    tasks=json.loads(readiness_path.read_text())['tasks'];pools={};inputs=[primary_path,readiness_path,Path(__file__),
        Path('local_deep_research/research_verify/bibliography_identity.py'),
        Path('local_deep_research/research_verify/report_syntax.py')]
    for task in tasks:
        p=Path(task['source_pack_path']);inputs.append(p)
        pool=json.loads(p.read_text());pools[task['task_id']]={str(i):r for i,r in enumerate(pool)}
    reports=[]
    for path in sorted(Path('evaluation/pane2-independent-review-20261113/nonimmune-sources/archive-reports').rglob('*.txt')):
        inputs.append(path);report=path.read_text();entries=bibliography_entries(report);rows=[]
        for entry in entries:
            source=match_identifiers(entry,primary_records)
            source['metadata_records']=[dict(record_key=r['record_key'],metadata=primary_records[r['record_key']],
                cached_record_body_sha256=primary[r['record_key']].get('body_sha256'),
                cached_record_url=primary[r['record_key']].get('url')) for r in source['matches']]
            reruns={task:match_identifiers(entry,records) for task,records in pools.items()}
            for task,result in reruns.items():
                for match in result['matches']:
                    match['rerun_source_id']=pools[task][match['record_key']].get('index')
            rows.append(dict(source_id=entry['source_id'],start=entry['start'],end=entry['end'],
                bibliography_entry_sha256=entry['sha256'],primary_cache=source,rerun_namespaces=reruns))
        reports.append(dict(report_path=str(path),entries=rows))
    receipt=dict(scope='Exact bibliography identifier equality only. No title/topic match, source truth, task equivalence, correction score or automatic namespace transfer.',
        inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},reports=reports,quality_claim=None)
    (args.out_dir/'crosswalk.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    for report in reports:
        rows=report['entries'];print(json.dumps(dict(report=report['report_path'],bibliography_entries=len(rows),
            unique_primary_record_matches=sum(r['primary_cache']['status']=='one_record_match' for r in rows),
            primary_conflicts=sum(r['primary_cache']['status']=='identifier_conflict' for r in rows),
            entries_with_any_rerun_identifier_match=sum(any(v['matches'] for v in r['rerun_namespaces'].values()) for r in rows)),ensure_ascii=False))


if __name__=='__main__':main()
