"""Finite exact-PII recovery from literal Cell archive URLs, no report changes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.original_reference import original_reference_urls
from research_verify.publisher_identity import publisher_url_pii, bind_original_pii, pubmed_pii_identity
from research_verify.source_identity import identity_fields
from research_verify.retrieval import xml_text


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def records(xml):
    result=[]
    for node in ET.fromstring(xml).findall('./PubmedArticle'):
        pmid=node.findtext('./MedlineCitation/PMID')
        dois={n.text for n in node.findall('./PubmedData/ArticleIdList/ArticleId')if n.get('IdType')=='doi'}
        if len(dois)!=1:continue
        doi=next(iter(dois))
        if not pubmed_pii_identity(xml,pmid=pmid,doi=doi):continue
        article=node.find('./MedlineCitation/Article')
        def text(path):
            n=article.find(path);return xml_text(n).strip()if n is not None else''
        abstract='\n\n'.join(((n.get('Label')+': ')if n.get('Label')else'')+xml_text(n).strip()for n in article.findall('./Abstract/AbstractText'))
        result.append(dict(pmid=pmid,doi=doi,title=text('./ArticleTitle'),journal=text('./Journal/Title'),
                           publication_year=text('./Journal/JournalIssue/PubDate/Year'),
                           abstract=abstract,source_material=abstract,
                           content_type='abstract'if abstract else'bibliographic_metadata_only',
                           link='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',
                           publication_types=[xml_text(n).strip()for n in article.findall('./PublicationTypeList/PublicationType')]))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    base=Path('evaluation/frontier-strategy-20261113')
    packs=sorted((base/'archive-pii-metadata-overlays-20261115-v1').glob('report-*/sources.json'))
    assert len(packs)==5
    cached=base/'xenium-pii-direct-live-20261115-v1/attempt/response-01.bin'
    cached_xml=cached.read_bytes();cached_records=records(cached_xml)
    originals={p.parent.name:json.loads(p.read_text())for p in packs};jobs=[]
    for pack,sources in originals.items():
        for source in sources:
            if identity_fields(source):continue
            anchors=original_reference_urls(source)
            piis={publisher_url_pii(x['url'])for x in anchors if 'cell.com/'in x['url']}-{None}
            if len(piis)==1:jobs.append(dict(pack=pack,source_id=source['index'],pii=next(iter(piis))))
    assert len(jobs)<=7
    cached_matches={}
    for job in jobs:
        source=next(s for s in originals[job['pack']]if s['index']==job['source_id'])
        matches=[(known,bind_original_pii(source,known,cached_xml))for known in cached_records]
        matches=[x for x in matches if x[1]]
        if len(matches)==1:cached_matches[(job['pack'],job['source_id'])]=matches[0]
    pii_set=sorted({job['pii']for job in jobs if(job['pack'],job['source_id'])not in cached_matches})
    terms=[]
    for pii in pii_set:
        punctuated=f'{pii[:5]}-{pii[5:9]}({pii[9:11]}){pii[11:16]}-{pii[16:]}'
        terms.extend(json.dumps(x)+'[aid]'for x in(pii,punctuated))
    query=' OR '.join(terms)
    paths=[*packs,cached,Path(__file__).resolve().relative_to(Path.cwd().resolve()),*Path('local_deep_research/research_verify').glob('*.py')]
    freeze={str(p):sha(p)for p in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for path in paths:
        if str(path).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    plan=dict(scope='Five frozen archive packs include immune and exclude RNA; only exact literal Cell PII identity gaps',jobs=jobs,source_records=sum(map(len,originals.values())),cached_matches=len(cached_matches),query=query,maximum_network_reads=2,maximum_candidate_pmids=10,model_calls=0,report_modifications=0,newly_credited_corrections=0)
    (a.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan,ensure_ascii=False));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});transport=[]
    class Recorded(EvidenceFetcher):
        def read_bytes(self,url,**kw):
            row=dict(index=len(transport),url=url,params=kw.get('params'));transport.append(row)
            try:
                raw=super().read_bytes(url,**kw);dest=a.out_dir/f"response-{row['index']:02d}.bin";dest.write_bytes(raw)
                row.update(status='retrieved',file=dest.name,bytes=len(raw),sha256=sha(dest));return raw
            except Exception as exc:
                row.update(status='unavailable',error_type=type(exc).__name__);raise
            finally:(a.out_dir/'transport.json').write_text(json.dumps(transport,indent=2)+'\n')
    fetch=Recorded(settings,seconds=40,requests=2);live_records=[];raw=None;search={};failure=None
    try:
        fetch.permit(engine='pubmed')
        search=json.loads(fetch.read('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',params=dict(db='pubmed',term=query,retmode='json',retmax=10),service='pubmed'))['esearchresult']
        ids=search.get('idlist',[])
        if not search.get('errorlist')and 0<len(ids)<=10 and int(search['count'])<=10:
            raw=fetch.read_bytes('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',params=dict(db='pubmed',id=','.join(ids),retmode='xml'),service='pubmed')
            live_records=[r for r in records(raw)if r['pmid']in ids]
    except Exception as exc:failure=type(exc).__name__
    output=copy.deepcopy(originals);outcomes=[]
    for job in jobs:
        key=(job['pack'],job['source_id']);before=next(s for s in originals[job['pack']]if s['index']==job['source_id'])
        matches=[]
        if key in cached_matches:
            known,proof=cached_matches[key];matches=[(known,proof,cached_xml,'previous_exact_own_pubmed_xml')]
        elif raw is not None:
            for known in live_records:
                proof=bind_original_pii(before,known,raw)
                if proof:matches.append((known,proof,raw,'new_exact_own_pubmed_xml'))
        if len(matches)==1:
            known,proof,xml,origin=matches[0];after=next(s for s in output[job['pack']]if s['index']==job['source_id'])
            for k,v in known.items():
                if v and(not after.get(k)or(k=='title'and str(after[k]).startswith('Unresolved original bibliography entry '))or(k=='content_type'and after[k]=='bibliographic_metadata_only')):after[k]=v
            after['previous_identity_binding']=before.get('identity_binding')
            after['identity_binding']=dict(proof,origin=origin,primary_xml_sha256=hashlib.sha256(xml).hexdigest())
            outcomes.append(dict(**job,status='exact_pii_identity_bound',proof=proof,origin=origin))
        else:outcomes.append(dict(**job,status='unresolved',matching_records=len(matches)))
    body_checks=[]
    for name,before in originals.items():
        after=output[name];assert [s['index']for s in before]==[s['index']for s in after]
        for left,right in zip(before,after,strict=True):
            for k,v in left.items():
                if k.startswith('original_')or k=='fetched_content':assert right[k]==v
            if left.get('fetched_content'):body_checks.append(dict(pack=name,source_id=left['index'],sha256=hashlib.sha256(left['fetched_content'].encode()).hexdigest()))
        folder=a.out_dir/name;folder.mkdir();(folder/'sources.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n')
    assert all(sha(Path(k))==v for k,v in freeze.items())
    receipt=dict(outcomes=outcomes,search=search,failure_type=failure,network_read_attempts=len(transport),prior_bodies_preserved=body_checks,source_ids_preserved=True,frozen_inputs_unchanged=True,model_calls=0,report_modifications=0,newly_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'jobs':len(jobs),'bound':sum(x['status']=='exact_pii_identity_bound'for x in outcomes),'network_read_attempts':len(transport),'failure_type':failure,'model_calls':0}))


if __name__=='__main__':main()
