"""No-model audit of actual source metadata transport and reviewer prompts."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.prepare_source_detail_material_20261114 import native_documents


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--plan-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    assembly_path=Path('evaluation/frontier-strategy-20261113/archive-identity-sourcepacks-20261114-v3/assembly-audit.json')
    assembly=json.loads(assembly_path.read_text());reports=[];sources_by_report=[]
    for row in assembly['reports']:
        path=Path(row['source_pack_path']);sources=json.loads(path.read_text());sources_by_report.append({int(s['index']):s for s in sources})
        docs=native_documents(sources);fields=[]
        for source,doc in zip(sources,docs,strict=True):
            fields.append(dict(source_id=source['index'],authors_provided=bool(source.get('authors')),
                authors_retained_in_document=doc.metadata.get('authors')==source.get('authors') if source.get('authors') else None,
                journal_provided=bool(source.get('journal')),
                journal_retained_in_document=doc.metadata.get('journal')==source.get('journal') if source.get('journal') else None,
                date_provided=bool(source.get('pubdate')),
                date_retained_in_document=doc.metadata.get('publication_date')==source.get('pubdate') if source.get('pubdate') else None))
        reports.append(dict(report_path=row['report_path'],source_pack_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fields=fields))
    plan=json.loads((a.plan_dir/'plan.json').read_text());jobs=[]
    for job in plan['jobs']:
        if job['status']!='prepared':continue
        material=(a.plan_dir/job['name']/'material.txt').read_text();prompt=(a.plan_dir/job['name']/'prompt.txt').read_text()
        assert hashlib.sha256(material.encode()).hexdigest()==job['material_sha256']
        assert hashlib.sha256(prompt.encode()).hexdigest()==job['prompt_sha256']
        fields=[]
        for index in job['visible_ids']:
            source=sources_by_report[job['report_index']][int(index)]
            fields.append(dict(source_id=index,
                authors_provided=bool(source.get('authors')),
                author_string_in_material=source['authors'] in material if source.get('authors') else None,
                journal_provided=bool(source.get('journal')),
                journal_header_in_material=('Journal: '+source['journal']+'\n') in material if source.get('journal') else None,
                date_header_in_material=('Date: '+source['pubdate']+'\n') in material if source.get('pubdate') else None))
        jobs.append(dict(name=job['name'],fields=fields,prompt_sha256=job['prompt_sha256'],material_sha256=job['material_sha256']))
    inputs=[Path(__file__),Path('scripts/prepare_source_detail_material_20261114.py'),
            Path('local_deep_research/overlay/base_citation_handler.py'),
            Path('local_deep_research/research_verify/generation.py')]
    for path in inputs:
        dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    out=dict(scope='Literal source-field transport and saved-prompt exposure only, not comprehension/identity truth or correction',
        inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},reports=reports,jobs=jobs,quality_claim=None)
    (a.out_dir/'audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    fields=[f for r in reports for f in r['fields']]
    print(json.dumps(dict(authors_provided=sum(f['authors_provided'] for f in fields),
        authors_retained=sum(f['authors_retained_in_document'] is True for f in fields),
        journal_retained=sum(f['journal_retained_in_document'] is True for f in fields),
        dates_retained=sum(f['date_retained_in_document'] is True for f in fields))))


if __name__=='__main__':main()
