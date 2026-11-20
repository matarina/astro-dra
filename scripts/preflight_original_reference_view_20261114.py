"""Replay an actual locator PDF through native supplementation and source views."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from research_verify.evidence_fetch import EvidenceFetcher
from research_verify.evidence_flow import supplement, review_claim_groups, _review_material
from scripts.prepare_source_detail_material_20261114 import native_documents
from scripts.run_native_original_report_pair_20261114 import Trace


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser()
    for name in ('sources','prior-attempt','acquisition','out-dir'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((a.acquisition/'receipt.json').read_text())
    raw=(a.acquisition/'document.bin').read_bytes()
    assert receipt['status']=='retrieved_and_extracted' and sha(raw)==receipt['raw_sha256']
    assert sha(a.sources.read_bytes())==receipt['source_pack_sha256']
    sources=json.loads(a.sources.read_text());original=copy.deepcopy(sources)
    index=int(receipt['anchor']['source_index']);requests=[]
    def get(url,**kw):
        assert url==receipt['anchor']['url'];requests.append(url)
        return SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[raw],close=lambda:None)
    fetch=EvidenceFetcher({'citation.original_reference_pdf_followup':True},get=get,requests=1)
    trace=Trace(a.out_dir/'trace.jsonl')
    acquired=supplement([dict(status='insufficient_evidence',source_id=index,request={'kind':'article'})],
                        sources,fetch,register=lambda s:None,trace=trace)
    assert acquired==[index] and len(requests)==1
    for before,after in zip(original,sources):
        assert before=={k:v for k,v in after.items()if k!='fetched_content'}
    query=json.loads((a.prior_attempt/'plan.json').read_text())['query']
    report=(a.prior_attempt/'original-report.txt').read_text()
    docs=native_documents(sources);groups=review_claim_groups(report,docs,sources,query,60000)
    rows=[]
    for n,group in enumerate(groups,1):
        required=set().union(*(set(c['source_ids'])for c in group.values()))
        if index not in required:continue
        material,_=_review_material(docs,query,group,required,60000)
        view=material.views[index]
        assert view['text'] in str(material) or view['block'] in str(material)
        (a.out_dir/f'group-{n:02d}-material.txt').write_text(str(material))
        (a.out_dir/f'group-{n:02d}-view.json').write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
        rows.append(dict(group=n,available_chars=view['available_chars'],model_view_chars=view['model_view_chars'],
            material_sha256=sha(str(material).encode()),view_sha256=sha(view['text'].encode()),
            locator_warning_visible='paper identity, requested eligibility' in view['text'],
            scope=view['scope']))
    assert rows and all(r['locator_warning_visible']for r in rows)
    (a.out_dir/'source-records.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    result=dict(scope='Offline replay of previously acquired PDF; native supplement and formatter exposure only',
        transport_origin='cached_original_locator_pdf; injected exact URL/byte replay; NO new HTTP',
        source_index=index,raw_sha256=sha(raw),source_pack_sha256=sha(a.sources.read_bytes()),
        source_identity_fields_unchanged=True,group_views=rows,model_calls=0,newly_credited_corrections=0,
        identity_status='original_reference_locator_only',quality_claim=None)
    (a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
