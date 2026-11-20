"""Finite original-PII identity recovery across frozen archive source packs.

Title queries discover candidates only. Acceptance requires own PubMed IDs;
no model calls, report rewrites, citation renumbering or source merging.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from research_verify.original_reference import original_reference_urls
from research_verify.publisher_identity import publisher_url_pii,bind_original_pii
from research_verify.source_identity import identity_fields
from research_verify.evidence_fetch import EvidenceFetcher,from_epmc
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113');packs=sorted((base/'archive-locator-sourcepacks-20261114-v2').glob('report-*/sources.json'));assert len(packs)==5
    cached_xml=base/'adipose-pii-identity-live-20261115-v1/response.bin';cached_receipt=base/'adipose-pii-identity-live-20261115-v1/receipt.json';assert sha(cached_xml)==json.loads(cached_receipt.read_text())['sha256']
    all_sources={str(pack):json.loads(pack.read_text())for pack in packs};jobs=[];prior=[]
    for pack,sources in all_sources.items():
        for source in sources:
            if identity_fields(source):continue
            urls=original_reference_urls(source);piis={publisher_url_pii(x['url'])for x in urls}-{None}
            if len(piis)!=1:continue
            known_matches=[]
            for known in sources:
                if not identity_fields(known):continue
                proof=bind_original_pii(source,known,cached_xml.read_bytes())
                if proof:known_matches.append((known,proof))
            row=dict(source_pack=pack,source_index=str(source['index']),pii=next(iter(piis)),original_reference_sha256=source['original_bibliography_sha256'])
            if known_matches:
                assert len({(proof['pmid'],proof['doi'])for _,proof in known_matches})==1
                known,proof=known_matches[0];prior.append(dict(row,known=known,proof=proof,origin='previous_exact_primary_xml'))
            else:
                title=source['original_bibliography_entry'].split('URL:',1)[0].split(']',1)[1].strip()
                if title.endswith(' ...'):title=title[:-4].rstrip()
                jobs.append(dict(row,title_prefix=title,query='TITLE:'+json.dumps(title,ensure_ascii=False)+' AND SRC:MED'))
    if len(jobs)>2:raise ValueError('Predeclared maximum two candidate-discovery reads')
    paths=[*packs,cached_xml,cached_receipt,Path(__file__),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py')]
    freeze={str(p):sha(p)for p in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='All five nonimmune original archive packs; only literal publisher PII identity gaps, not six-task scientific coverage',source_packs=len(packs),source_records=sum(map(len,all_sources.values())),previous_exact_bindings=len(prior),candidate_searches=jobs,maximum_network_reads=3,maximum_candidate_pmids=10,model_calls=0,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan,ensure_ascii=False));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})
    transport=[]
    class Recorded(EvidenceFetcher):
        def read_bytes(self,url,**kw):
            event=dict(index=len(transport),url=url,params=kw.get('params'));transport.append(event)
            try:
                raw=super().read_bytes(url,**kw);path=a.out_dir/f"response-{event['index']:02d}.bin";path.write_bytes(raw);event.update(status='retrieved',file=path.name,sha256=sha(path),bytes=len(raw));return raw
            except Exception as exc:event.update(status='unavailable',**error_receipt(exc));raise
    fetch=Recorded(settings,seconds=40,requests=3);candidates={};outcomes=[]
    for job in jobs:
        row=dict(job,candidates=[],status='unresolved')
        try:
            fetch.permit(engine='europepmc');data=json.loads(fetch.read('https://www.ebi.ac.uk/europepmc/webservices/rest/search',params=dict(query=job['query'],resultType='core',format='json',pageSize=5),service='europepmc'))
            row['hit_count']=data.get('hitCount');row['candidate_search_truncated']=int(data.get('hitCount',0))>5
            for record in data.get('resultList',{}).get('result',[]):
                if record.get('source')!='MED':continue
                known=from_epmc(record);known.update(authors=record.get('authorString',''),publication_year=record.get('pubYear',''),publication_status=record.get('publicationStatus',''))
                ids=identity_fields(known)
                if not(ids.get('pmid')and ids.get('doi')):continue
                candidates[ids['pmid']]=known;row['candidates'].append(ids['pmid'])
        except Exception as exc:row.update(discovery_failure=error_receipt(exc))
        outcomes.append(row)
    if len(candidates)>10:raise ValueError('Candidate PMID bound')
    xml=None
    if candidates:
        try:
            fetch.permit(engine='pubmed');xml=fetch.read_bytes('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',params=dict(db='pubmed',id=','.join(sorted(candidates)),retmode='xml'),service='pubmed')
        except Exception as exc:(a.out_dir/'primary_lookup_failure.json').write_text(json.dumps(error_receipt(exc),indent=2)+'\n')
    resolved=list(prior)
    for row in outcomes:
        source=next(s for s in all_sources[row['source_pack']]if str(s['index'])==row['source_index']);matches=[]
        if xml:
            for pmid in row['candidates']:
                known=candidates[pmid];proof=bind_original_pii(source,known,xml)
                if proof:matches.append((known,proof))
        if len(matches)==1:
            known,proof=matches[0];resolved.append(dict(row,known=known,proof=proof,origin='fresh_pubmed_own_article_ids'));row.update(status='exact_pii_identity_bound',proof=proof)
        elif matches:row['status']='unresolved_multiple_matching_records'
    outputs=[]
    for pack,original in all_sources.items():
        sources=copy.deepcopy(original);changed=[]
        for item in resolved:
            if item['source_pack']!=pack:continue
            target=next(s for s in sources if str(s['index'])==item['source_index']);known=item['known'];before=copy.deepcopy(target)
            for field in ('title','doi','pmid','pmcid','journal','pubdate','publication_year','language','authors','publication_types','publication_status','abstract','source_material','link'):
                missing=not target.get(field)or(field=='title'and str(target[field]).startswith('Unresolved original bibliography entry '))
                value=known.get(field)or(known.get('abstract')if field=='source_material'else None)
                if missing and value:target[field]=copy.deepcopy(value)
            if target.get('abstract')and before.get('content_type')=='bibliographic_metadata_only':target['content_type']='abstract'
            target['previous_identity_binding']=before.get('identity_binding');target['identity_binding']=dict(item['proof'],origin=item['origin'],input_source_pack_sha256=sha(Path(pack)))
            assert all(target[k]==before[k]for k in before if k.startswith('original_'))
            changed.append(item['source_index'])
        assert len(sources)==len(original)and [s['index']for s in sources]==[s['index']for s in original]
        folder=a.out_dir/Path(pack).parent.name;folder.mkdir();dest=folder/'sources.json';dest.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n');outputs.append(dict(input=pack,input_sha256=sha(Path(pack)),output=str(dest),output_sha256=sha(dest),changed_source_indices=changed,source_count=len(sources)))
    assert all(sha(Path(p))==h for p,h in freeze.items())
    result=dict(scope=plan['scope'],outcomes=outcomes,previous_exact_bindings=[{k:v for k,v in x.items()if k!='known'}for x in prior],outputs=outputs,transport=transport,frozen_inputs_unchanged=True,model_calls=0,report_modifications=0,source_ids_preserved=True,no_source_merge=True,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(network_reads=len(transport),outcomes=[dict(source_index=x['source_index'],status=x['status'])for x in outcomes],outputs=outputs)))


if __name__=='__main__':main()
