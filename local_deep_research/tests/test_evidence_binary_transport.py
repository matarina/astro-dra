from types import SimpleNamespace
import pytest
from research_verify.evidence_fetch import EvidenceFetcher


def test_binary_document_preserved_and_text_wrapper_keeps_previous_decode():
    raw=b'%PDF-1.7\n\xff\x00\x80';closed=[]
    def get(*a,**kw):return SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[raw[:4],raw[4:]],close=lambda:closed.append(True))
    fetch=EvidenceFetcher(get=get,requests=2)
    assert fetch.read_bytes('https://example.org/paper.pdf')==raw
    assert fetch.read('https://example.org/text')==raw.decode('utf-8',errors='replace')
    assert fetch.remaining==0 and len(closed)==2


def test_binary_path_retains_response_bound_and_closes_on_failure():
    closed=[]
    response=SimpleNamespace(raise_for_status=lambda:None,iter_content=lambda size:[b'12345'],close=lambda:closed.append(True))
    fetch=EvidenceFetcher(get=lambda *a,**kw:response,requests=1)
    with pytest.raises(TimeoutError):fetch.read_bytes('https://example.org/paper.pdf',limit=4)
    assert closed==[True]and fetch.remaining==0
