"""Regression seams for paragraph evidence, independent web lookup and review state."""
import json
from types import SimpleNamespace

from research_verify.evidence_flow import review_claim_groups, supplement, parse_review, apply_review
from research_verify.generation import format_source_documents
from research_verify.synthesis_trace import DISABLED
from test_generation_grounding import handler


def test_paragraph_citation_scope_and_formatted_labels_are_preserved():
    text='## Results\n\n**Measurements**:\n\nCounts increased in the treated group. The change was measured at day three [7].'
    groups=review_claim_groups(text,[],[{'index':7}],'Question',60000)
    claims=[c for group in groups for c in group.values()]
    assert len(claims)==1
    assert claims[0]['text']=='Counts increased in the treated group. The change was measured at day three [7].'
    assert claims[0]['source_ids']==[7]
    assert '**Measurements**:' in claims[0]['section_context']


def test_uncited_substantive_assertions_remain_reviewable():
    text='## Measurements\n\n**Results**:\n\nThe method cannot detect protein molecules.'
    claims=[c for g in review_claim_groups(text,[],[],'Question',60000) for c in g.values()]
    assert len(claims)==1 and claims[0]['text']=='The method cannot detect protein molecules.'


def test_report_framing_status_applies_only_to_uncited_text():
    response='{"issues":[{"claim_id":0,"status":"report_context"}]}'
    assert parse_review(response,{0:{'text':'The report is organized into three sections.','source_ids':[]}})==[]
    pending=parse_review(response,{0:{'text':'Population A was measured [7].','source_ids':[7]}})
    assert pending and pending[0]['status']!='report_context'


def test_new_primary_web_document_does_not_require_an_existing_paper_number():
    class Fetch:
        calls=0
        def web(self,*args):
            self.calls+=1
            return [{'title':'Primary technical specification','link':'https://example.org/spec',
                     'content':'The instrument measures property Q.'}]
    fetch=Fetch();sources=[]
    acquired=supplement([{'source_id':None,'status':'insufficient_evidence',
        'request':{'kind':'web','query':'Primary technical specification'}}],sources,fetch,register=None,trace=DISABLED)
    assert fetch.calls==1 and acquired==[1] and sources[0]['link']=='https://example.org/spec'


def test_unbound_article_request_does_not_guess_a_paper():
    fetch=SimpleNamespace(article=lambda _:(_ for _ in ()).throw(AssertionError('No paper ID')))
    assert supplement([{'source_id':None,'status':'insufficient_evidence','request':{'kind':'article'}}],
        [],fetch,register=None,trace=DISABLED)==[]


def test_explicit_contradiction_keeps_exact_atomic_quote_despite_summarized_overall_quote():
    raw={'issues':[{'claim_id':0,'evidence_source_id':7,'status':'contradiction',
        'evidence_quote':'Population A... method M',
        'atom_checks':[{'attribute':'population','result':'contradiction',
            'evidence_quote':'We studied population A.'}],
        'replacement':'We studied population A [7].'}]}
    original='We studied population B [7].'
    issues=parse_review(json.dumps(raw),{0:{'text':original,'source_ids':[7]}})
    material=format_source_documents([SimpleNamespace(page_content='We studied population A. Method M was used.',
        metadata={'index':7,'title':'Study','source':'https://example.org/study'})])
    revised,eligible,_=apply_review(original,issues,material)
    assert eligible and revised=='We studied population A [7].'
    assert eligible[0]['unlocated_quote_count']==1


def test_document_level_not_reported_is_an_evidence_gap_with_a_valid_request():
    raw={'issues':[{'claim_id':0,'status':'not_reported','evidence_source_id':7,'request':None}]}
    issues=parse_review(json.dumps(raw),{0:{'text':'A specific finding [7].','source_ids':[7]}})
    assert issues[0]['status']=='insufficient_evidence'
    assert issues[0]['reviewer_status']=='not_reported'
    assert issues[0]['request']['kind']=='article'


def test_supporting_candidate_is_not_automatically_the_missing_clause_article():
    raw = {'issues': [{'claim_id': 0, 'status': 'supported', 'evidence_source_id': 7,
        'evidence_sources': [{'source_id': 7, 'quote': 'Population A used method M.'}],
        'atom_checks': [{'attribute': 'method', 'claim_value': 'Population B used M',
                         'source_value': 'not reported', 'evidence_quote': '', 'result': 'not_reported'}]}]}
    claims = {0: {'text': 'Populations A and B used M.', 'source_ids': []}}
    issue, = parse_review(json.dumps(raw), claims)
    assert issue['status'] == 'insufficient_evidence'
    assert issue['source_id'] == 7  # Preserve provenance of the supplied clause.
    assert issue['request']['kind'] == 'web'
    assert claims[0]['source_ids'] == []
    cited = {0: {'text': 'Populations A and B used M [7].', 'source_ids': [7]}}
    issue, = parse_review(json.dumps(raw), cited)
    assert issue['request']['kind'] == 'article'


def test_unasserted_attributes_do_not_create_evidence_gaps():
    raw={'issues':[{'claim_id':0,'status':'supported','evidence_source_id':7,
        'atom_checks':[{'attribute':'method','claim_value':'method M','result':'supported'},
                       {'attribute':'population','claim_value':None,'result':'not_reported'}]}]}
    claims={0:{'text':'Method M was used [7].','source_ids':[7]}}
    assert parse_review(json.dumps(raw),claims)==[]
    raw['issues'][0]['atom_checks'][1]['claim_value']='population A'
    assert parse_review(json.dumps(raw),claims)[0]['status']=='insufficient_evidence'


def test_supplied_material_scope_assertion_is_not_a_full_paper_evidence_gap():
    raw = {'issues': [{'claim_id': 0, 'status': 'supported', 'evidence_source_id': 7,
        'atom_checks': [{'attribute': 'platform',
                         'attribute_role': 'platform',
                         'claim_value': 'not reported in the supplied material',
                         'source_value': 'not reported',
                         'evidence_quote': 'Spatial transcriptomics was used; platform not specified.',
                         'result': 'supported'}]}]}
    claims = {0: {'text': 'The supplied material does not report the spatial platform [7].',
                  'source_ids': [7]}}
    assert parse_review(json.dumps(raw), claims) == []


def test_table_repair_must_keep_the_original_column_structure():
    original='| Dataset | Used 72 samples for training | [7] |'
    material=format_source_documents([SimpleNamespace(page_content='We validated the method on 72 samples.',
        metadata={'index':7,'title':'Method','source':'https://example.org/method'})])
    issue={'statement':original,'source_id':7,'status':'contradiction',
        'evidence_quote':'We validated the method on 72 samples.',
        'replacement':'We validated the method on 72 samples [7].'}
    out,applied,pending=apply_review(original,[issue],material)
    assert out==original and not applied and pending[0]['format_issue']=='table_shape_changed'
    valid={**issue,'replacement':'| Dataset | Used 72 samples for validation | [7] |'}
    assert apply_review(original,[valid],material)[0]==valid['replacement']


def _version_review(approve_after_supplement):
    class Fetch:
        calls=0
        def article(self,source):
            self.calls+=1
            return 'The published procedure measures property Q. Additional method detail is available.'
    class Model:
        confirmations=0
        reviews=0
        def invoke(self,prompt):
            if 'Previous Knowledge:' in prompt:
                return SimpleNamespace(content='The procedure measures property Q [1][2].')
            if prompt.startswith('Check these numbered claims'):
                self.reviews+=1
                if self.reviews==1:
                    return SimpleNamespace(content=json.dumps({'issues':[{'claim_id':0,'evidence_source_id':2,
                        'status':'insufficient_evidence','request':{'kind':'article','query':'Method detail'}}]}))
                return SimpleNamespace(content=json.dumps({'issues':[{
                    'claim_id':0, 'status':'supported', 'evidence_source_id':2,
                    'evidence_quote':'The published procedure measures property Q.',
                }]}))
            self.confirmations+=1
            approve=self.confirmations==2 and approve_after_supplement
            return SimpleNamespace(content=json.dumps({'decisions':[{'candidate_index':0,
                'original_supported':True,'replacement_supported':approve,'same_analysis':approve}]}))
    model=Model();writer=handler(model);writer.settings_snapshot={'general.enable_fact_checking':True}
    fetch=Fetch();writer.evidence_fetcher=fetch
    sources=[{'index':1,'abstract':'The earlier procedure measures property Q.',
        'publication_versions':[{'index':2,'relation_type':'update_in'}],'version_resolution':'Already linked'},
        {'index':2,'abstract':'The published procedure measures property Q.'}]
    result=writer.analyze_followup('Question',sources,'Draft [1][2].',0)
    return result,model,fetch


def test_declined_version_candidate_survives_a_supported_general_rereview():
    result,model,fetch=_version_review(False)
    assert fetch.calls==1 and model.reviews==2
    pending=result['evidence_review']['parts'][0]['unresolved']
    assert any(i.get('issue_type')=='version_update' for i in pending)
    assert result['content']=='The procedure measures property Q [1][2].'


def test_version_candidate_is_reconsidered_after_new_evidence_and_can_resolve(native_review_only):
    result,model,fetch=_version_review(True)
    assert model.confirmations==2 and fetch.calls==1
    assert result['content']=='The procedure measures property Q [2].'
    assert not result['evidence_review']['parts'][0]['unresolved']
