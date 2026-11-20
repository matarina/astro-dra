"""Prepare original citation namespaces from exact-matched API metadata.

These are newly acquired experimental inputs, not the original production
writer material and not independently adjudicated report corrections.
"""
import argparse
import hashlib
import json
from pathlib import Path
from research_verify.bibliography_identity import bibliography_entries,match_identifiers
from research_verify.retrieval import html_text


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--crosswalk',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True);parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--supplement-metadata',type=Path)
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=False)
    cross=json.loads(args.crosswalk.read_text());metadata_paths=[args.metadata]
    if args.supplement_metadata:metadata_paths.append(args.supplement_metadata)
    records={};record_inputs={}
    for p in metadata_paths:
        for key,record in json.loads(p.read_text())['records'].items():
            if key in records and records[key]!=record:raise ValueError('Conflicting snapshots for an API record; review before assembly')
            records[key]=record;record_inputs[key]=p
    rows=[];inputs=[args.crosswalk,*metadata_paths,Path(__file__)]
    for i,report in enumerate(cross['reports']):
        path=Path(report['report_path']);inputs.append(path);text=path.read_text()
        original_entries=bibliography_entries(text)
        if any(not e['source_id_unique'] for e in original_entries):
            raise ValueError('Nonunique original bibliography IDs; cannot prepare an unambiguous source namespace')
        originals={e['source_id']:e for e in original_entries}
        sources=[];bindings=[]
        for entry in report['entries']:
            index=entry['source_id'];new=match_identifiers(originals[index],records);old=entry['primary_cache'];record={};origin={}
            if new['status']=='one_record_match' and old['status'] not in {'identifier_conflict','nonunique_bibliography_source_id'}:
                key=new['matches'][0]['record_key'];record=records[key]
                origin=dict(kind='new_europepmc_core_record',record_key=key,input_path=str(record_inputs[key]),input_sha256=digest(record_inputs[key]))
            elif old['status']=='one_record_match' and new['status']=='no_identifier_match':
                cached=old['metadata_records'][0];record=cached['metadata']
                origin=dict(kind='existing_primary_metadata_cache',record_key=cached['record_key'],
                    cached_record_body_sha256=cached['cached_record_body_sha256'],cached_record_url=cached['cached_record_url'])
            abstract=html_text(record.get('abstractText') or '')
            journal=(record.get('journalInfo') or {}).get('journal') or {}
            source=dict(index=index,title=record.get('title') or f'Unresolved original bibliography entry {index}',
                doi=record.get('doi') or '',pmid=record.get('pmid') or '',pmcid=record.get('pmcid') or '',
                journal=journal.get('title') or record.get('journalTitle') or '',
                pubdate=record.get('firstPublicationDate') or '',publication_year=record.get('pubYear') or '',
                language=record.get('language') or '',authors=record.get('authorString') or '',
                publication_types=(record.get('pubTypeList') or {}).get('pubType') or record.get('pubType') or [],
                publication_status=record.get('publicationStatus') or '',
                abstract=abstract,source_material=abstract,
                content_type='abstract' if abstract else 'bibliographic_metadata_only',
                original_bibliography_entry=originals[index]['text'],
                original_bibliography_sha256=originals[index]['sha256'],
                identity_binding=origin or dict(kind='unresolved',fresh_status=new['status'],cached_status=old['status']))
            if record.get('source') and record.get('id'):
                source['link']='https://europepmc.org/article/'+str(record['source'])+'/'+str(record['id'])
            if record:
                source['identity_binding']['record_sha256']=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            sources.append(source);bindings.append(dict(source_id=index,status='metadata_record_bound' if record else 'unresolved',article_text_scope=source['content_type']))
        destination=args.out_dir/f'report-{i:02d}';destination.mkdir();pack=destination/'sources.json'
        pack.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
        rows.append(dict(report_path=str(path),original_report_sha256=digest(path),source_pack_path=str(pack),
            source_pack_sha256=digest(pack),sources=len(sources),bound_metadata=sum(b['status']=='metadata_record_bound' for b in bindings),
            with_abstract=sum(b['article_text_scope']=='abstract' for b in bindings),bindings=bindings))
    inputs.extend(Path('local_deep_research/research_verify')/n for n in ['bibliography_identity.py','report_syntax.py','retrieval.py'])
    for p in inputs:
        if str(p).startswith(('scripts/','local_deep_research/')):
            dest=args.out_dir/'code'/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    (args.out_dir/'assembly-audit.json').write_text(json.dumps(dict(
        scope='Original bibliography namespace with newly acquired exact-identifier metadata/abstracts; no original-production-material equivalence, no full-text acquisition, no task outcome or correction score',
        inputs={str(p):digest(p) for p in inputs},reports=rows,quality_claim=None),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(report=r['report_path'],sources=r['sources'],metadata=r['bound_metadata'],abstracts=r['with_abstract']) for r in rows],ensure_ascii=False))


if __name__=='__main__':main()
