"""Offline original-locator metadata enrichment from own PubMed article IDs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from research_verify.publisher_identity import bind_original_pii


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--known-index',required=True);p.add_argument('--pubmed-xml',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    paths=[a.sources,a.pubmed_xml,Path(__file__),Path('local_deep_research/research_verify/publisher_identity.py'),Path('local_deep_research/research_verify/source_identity.py'),Path('local_deep_research/research_verify/original_reference.py')]
    freeze={str(x):sha(x)for x in paths};(a.out_dir/'prestart-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    original=json.loads(a.sources.read_text());sources=copy.deepcopy(original);known=next(x for x in original if str(x['index'])==a.known_index);xml=a.pubmed_xml.read_bytes();bindings=[]
    for before,after in zip(original,sources,strict=True):
        if str(before['index'])==a.known_index:continue
        proof=bind_original_pii(before,known,xml)
        if not proof:continue
        fields=[]
        for k in ('title','doi','pmid','pmcid','journal','pubdate','publication_year','language','authors','publication_types','publication_status','abstract','source_material','link'):
            missing=not before.get(k)or(k=='title'and str(before[k]).startswith('Unresolved original bibliography entry '))
            if missing and known.get(k):after[k]=copy.deepcopy(known[k]);fields.append(k)
        if 'abstract'in fields and before.get('content_type')=='bibliographic_metadata_only':after['content_type']='abstract';fields.append('content_type')
        after['previous_identity_binding']=copy.deepcopy(before.get('identity_binding'))
        after['identity_binding']=dict(proof,primary_xml=str(a.pubmed_xml),primary_xml_sha256=sha(a.pubmed_xml),known_record_source_pack_sha256=sha(a.sources))
        assert after['index']==before['index'] and after['original_bibliography_entry']==before['original_bibliography_entry'] and after['original_bibliography_sha256']==before['original_bibliography_sha256']
        bindings.append(dict(proof=proof,filled_fields=fields))
    assert len(sources)==len(original)and all(sha(Path(p))==h for p,h in freeze.items())
    (a.out_dir/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    result=dict(scope='Exact PII/PubMed identity metadata enrichment only; stable source IDs retained, no merge/report edits or scientific support inference',bindings=bindings,input_sha256=sha(a.sources),output_sha256=sha(a.out_dir/'sources.json'),source_count=len(sources),code_input_hashes_unchanged=True,model_calls=0,network_calls=0,report_modifications=0,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
