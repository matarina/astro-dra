"""Two-read exact-PII discovery and own-article identity binding via PubMed."""
import argparse,copy,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.original_reference import original_reference_urls
from research_verify.publisher_identity import publisher_url_pii,bind_original_pii
from research_verify.retrieval import xml_text
from scripts.experiment_error_receipt import error_receipt


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--source-id',required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    original=json.loads(a.sources.read_text());source=next(s for s in original if str(s['index'])==a.source_id);piis={publisher_url_pii(u['url'])for u in original_reference_urls(source)}-{None}
    if len(piis)!=1:raise ValueError('One literal original PII required')
    pii=next(iter(piis));punctuated=f'{pii[:5]}-{pii[5:9]}({pii[9:11]}){pii[11:16]}-{pii[16:]}'
    query=' OR '.join(json.dumps(x)+'[aid]'for x in (pii,punctuated))
    files=[a.sources,Path(__file__),Path('scripts/experiment_error_receipt.py'),*Path('local_deep_research/research_verify').glob('*.py')];freeze={str(p):sha(p)for p in files};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    for file in files:
        if str(file).startswith(('scripts/','local_deep_research/')):
            dest=a.out_dir/'code'/file;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(file.read_bytes())
    plan=dict(source_id=a.source_id,original_pii=pii,query=query,maximum_reads=2,maximum_candidate_pmids=5,scope='Exact original identifier query, acceptance only own PubMed PII/PMID/DOI; no model or report edits')
    (a.out_dir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    if not a.execute:print(json.dumps(plan));return
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text());settings=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()});transport=[]
    class Recorded(EvidenceFetcher):
        def read_bytes(self,url,**kw):
            row=dict(index=len(transport),url=url,params=kw.get('params'));transport.append(row)
            try:
                raw=super().read_bytes(url,**kw);dest=a.out_dir/f"response-{row['index']:02d}.bin";dest.write_bytes(raw);row.update(status='retrieved',file=dest.name,sha256=sha(dest),bytes=len(raw));return raw
            except Exception as exc:row.update(status='unavailable',**error_receipt(exc));raise
    fetch=Recorded(settings,seconds=30,requests=2);sources=copy.deepcopy(original);result=dict(status='unresolved',proof=None,candidates=[])
    try:
        fetch.permit(engine='pubmed');data=json.loads(fetch.read('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',params=dict(db='pubmed',term=query,retmode='json',retmax=5),service='pubmed'))['esearchresult'];result['search_response']=data;ids=data.get('idlist',[]);result['candidates']=ids
        if ids and not data.get('errorlist'):
            raw=fetch.read_bytes('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',params=dict(db='pubmed',id=','.join(ids),retmode='xml'),service='pubmed');matches=[]
            for node in ET.fromstring(raw).findall('./PubmedArticle'):
                pmid=node.findtext('./MedlineCitation/PMID');dois={x.text for x in node.findall('./PubmedData/ArticleIdList/ArticleId')if x.get('IdType')=='doi'}
                if pmid not in ids or len(dois)!=1:continue
                article=node.find('./MedlineCitation/Article')
                def text(path):
                    value=article.find(path);return xml_text(value).strip()if value is not None else ''
                abstract='\n\n'.join(((x.get('Label')+': ')if x.get('Label')else '')+xml_text(x).strip()for x in article.findall('./Abstract/AbstractText'))
                year=text('./Journal/JournalIssue/PubDate/Year')
                known=dict(pmid=pmid,doi=next(iter(dois)),title=text('./ArticleTitle'),journal=text('./Journal/Title'),publication_year=year,abstract=abstract,source_material=abstract,content_type='abstract'if abstract else'bibliographic_metadata_only',link='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/',publication_types=[xml_text(x).strip()for x in article.findall('./PublicationTypeList/PublicationType')])
                proof=bind_original_pii(source,known,raw)
                if proof:matches.append((known,proof))
            if len(matches)==1:
                known,proof=matches[0];after=next(s for s in sources if str(s['index'])==a.source_id)
                for k,v in known.items():
                    if v and(not after.get(k)or(k=='title'and str(after[k]).startswith('Unresolved original bibliography entry '))or(k=='content_type'and after[k]=='bibliographic_metadata_only')):after[k]=v
                after['previous_identity_binding']=source.get('identity_binding');after['identity_binding']=dict(proof,primary_xml_sha256=hashlib.sha256(raw).hexdigest(),origin='fresh_pubmed_identifier_query_own_article_ids')
                assert all(after[k]==source[k]for k in source if k.startswith('original_'))
                result.update(status='exact_pii_identity_bound',proof=proof)
            elif matches:result['status']='unresolved_multiple_matching_records'
    except Exception as exc:result['failure']=error_receipt(exc)
    assert all(sha(Path(p))==h for p,h in freeze.items())and [s['index']for s in original]==[s['index']for s in sources]
    dest=a.out_dir/'sources.json';dest.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n');result.update(transport=transport,output_sha256=sha(dest),source_ids_preserved=True,source_count=len(sources),frozen_inputs_unchanged=True,model_calls=0,report_modifications=0,quality_claim=None,newly_credited_corrections=0);(a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
