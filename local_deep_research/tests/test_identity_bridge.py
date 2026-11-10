"""Exact biomedical identifier bridges; metadata is never article evidence."""
import json
from types import SimpleNamespace

from research_verify.evidence_fetch import EvidenceFetcher


def test_pmc_only_metadata_lookup_checks_the_requested_article():
    fetcher=EvidenceFetcher({})
    fetcher.permit=lambda **kw:None
    seen=[]
    def read(url,**kwargs):
        seen.append(kwargs['params']['query'])
        return json.dumps({'resultList':{'result':[
            {'source':'MED','id':'12','pmcid':'PMC99','doi':'10.1234/wrong'},
            {'source':'MED','id':'11','pmcid':'PMC22','doi':'10.1234/right'}]}})
    fetcher.read=read
    record=fetcher.record({'link':'https://pmc.ncbi.nlm.nih.gov/articles/PMC22/'})
    assert record and record['id']=='11' and seen==['PMCID:PMC22']


def test_exact_bridge_updates_only_identifiers_and_preserves_records():
    from research_verify.evidence_fetch import resolve_source_identities
    sources=[{'index':'7','pmid':'11','doi':'10.1234/right','abstract':'Original abstract.'},
             {'index':'9','link':'https://pmc.ncbi.nlm.nih.gov/articles/PMC22/','content':'Metadata only.'},
             {'index':'10','link':'https://pmc.ncbi.nlm.nih.gov/articles/PMC33/'}]
    seen=[]
    def record(source):
        seen.append(source['index'])
        return {'source':'MED','id':'11','pmcid':'PMC22','doi':'10.1234/right',
                'abstractText':'Do not substitute this fetched abstract.'}
    resolve_source_identities(sources,SimpleNamespace(record=record),required_ids={7,9})
    assert seen==['9'] and len(sources)==3
    assert sources[1]['pmid']=='11' and sources[0]['pmcid']=='PMC22'
    assert sources[1]['content']=='Metadata only.' and 'abstract' not in sources[1]
    assert 'pmid' not in sources[2]
    from research_verify.publication import publish_report
    from research_verify.config import VerifyConfig
    report=publish_report('The study reported its findings [7, 9].',sources,
                          cfg=VerifyConfig(enable_citation_qc=False))
    assert len(report.sources)==1 and report.sources[0].original_indices==[7,9]


def test_conflicting_or_failed_bridge_leaves_original_identity_intact():
    from research_verify.evidence_fetch import resolve_source_identities
    source={'index':7,'pmcid':'PMC22','content':'Original snapshot.'}
    for record in [lambda s:{'source':'MED','id':'11','pmcid':'PMC99'},
                   lambda s:(_ for _ in ()).throw(TimeoutError())]:
        sources=[dict(source)]
        resolve_source_identities(sources,SimpleNamespace(record=record),required_ids={7})
        assert sources==[source]


def test_converter_fallback_requires_an_exact_pmc_identifier():
    fetcher=EvidenceFetcher({});fetcher.permit=lambda **kw:None
    fetcher.read=lambda *a,**kw:json.dumps({'records':[
        {'pmcid':'PMC99','pmid':'12'}, {'pmcid':'PMC22','pmid':'11','doi':'10.1234/right'}]})
    assert fetcher.pmc_identifiers('PMC22')=={'pmcid':'PMC22','pmid':'11','doi':'10.1234/right'}


def test_partial_service_metadata_uses_converter_without_replacing_text():
    from research_verify.evidence_fetch import resolve_source_identities
    sources=[{'index':7,'pmcid':'PMC22','content':'Original snapshot.'}]
    fetcher=SimpleNamespace(record=lambda s:{'source':'PMC','id':'PMC22','pmcid':'PMC22'},
        pmc_identifiers=lambda s:{'pmcid':'PMC22','pmid':'11','doi':'10.1234/right'})
    resolve_source_identities(sources,fetcher,required_ids={7})
    assert sources[0]['pmid']=='11' and sources[0]['content']=='Original snapshot.'
