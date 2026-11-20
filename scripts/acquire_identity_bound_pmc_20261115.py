"""One explicit primary acquisition; never mutate a source pack or report."""
import argparse
import hashlib
import json
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from research_verify.pmc_identity import article_text
from scripts.experiment_error_receipt import error_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pack',type=Path,required=True)
    parser.add_argument('--source-id',type=int,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args();args.out_dir.mkdir(exist_ok=False)
    source,=[row for row in json.loads(args.source_pack.read_text()) if int(row['index'])==args.source_id]
    expected={key:source[key] for key in ['pmid','pmcid','doi']}
    assert expected['pmcid'].startswith('PMC') and expected['pmcid'][3:].isdigit()
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/'+expected['pmcid']+'/fullTextXML'
    files=[args.source_pack,Path(__file__).resolve(),Path('local_deep_research/research_verify/pmc_identity.py'),Path('scripts/experiment_error_receipt.py')]
    frozen={str(path):sha(path) for path in files}
    write(args.out_dir/'prestart-freeze.json',frozen)
    write(args.out_dir/'plan.json',dict(source_id=args.source_id,expected_own_article_ids=expected,url=url,maximum_network_requests=1,model_calls=0,ssl_verification=True,purpose='New primary source investigation, not retroactive evidence supplied to an earlier Writer or reviewer. No report/source-pack edits or semantic correction credit.'))
    failure=None;result={}
    try:
        context=ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt')
        request=urllib.request.Request(url,headers={'User-Agent':'Astro-DRA identity-bound source investigation'})
        with urllib.request.urlopen(request,context=context,timeout=40) as response:
            raw=response.read(5_000_001);assert len(raw)<=5_000_000
            result.update(http_status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'))
        (args.out_dir/'article.xml').write_bytes(raw)
        assert result['http_status']==200
        tree=ET.fromstring(raw);meta=tree.find('.//article-meta');assert meta is not None
        ids={node.get('pub-id-type'):''.join(node.itertext()).strip() for node in meta.findall('article-id')}
        assert ids['pmid']==expected['pmid'] and ids['pmcid']==expected['pmcid'] and ids['doi'].lower()==expected['doi'].lower()
        text=article_text(raw.decode('utf-8'),{'pmcid':expected['pmcid'],'doi':expected['doi']},pmid=expected['pmid'],require_body=True)
        assert text
        (args.out_dir/'article-text.txt').write_text(text)
        result.update(status='acquired_identity_bound_body',own_article_ids=ids,raw_bytes=len(raw),raw_sha256=sha(args.out_dir/'article.xml'),body_chars=len(text),body_sha256=sha(args.out_dir/'article-text.txt'))
    except Exception as error:
        failure=error_receipt(error);result.update(status='unavailable',failure=failure)
    result.update(model_calls=0,source_pack_unchanged=sha(args.source_pack)==frozen[str(args.source_pack)],frozen_inputs_unchanged=all(sha(Path(path))==value for path,value in frozen.items()),whole_published_paper_completeness_unconfirmed=True,report_edits=0,new_independent_correction_credit=0)
    for path in files[1:]:
        target=args.out_dir/'code'/path.name;target.parent.mkdir(exist_ok=True);target.write_bytes(path.read_bytes())
    write(args.out_dir/'result.json',result);print(json.dumps(result))
    if failure:raise SystemExit(2)


if __name__=='__main__':main()
