"""General evidence continuity, version provenance and final-text repair seams."""
from types import SimpleNamespace
import pytest
from research_verify.generation import format_source_documents
from research_verify.retrieval import html_text
from research_verify.evidence_flow import apply_review, writing_batches, parse_review, review_claim_groups, supplement
from research_verify.evidence_fetch import resolve_versions, EvidenceFetcher, register_source
from research_verify.synthesis_trace import DISABLED
import json
import copy
from test_generation_grounding import handler


def doc(i, text):
    return SimpleNamespace(page_content=text, metadata={'index':i,'title':f'Study {i}','source':f'https://example.org/{i}','abstract':text})

def test_existing_draft_citations_reserve_original_material_before_selection():
    docs=[doc(1,'Original supporting abstract. '*15),doc(2,'Other candidate. '*60)]
    text=format_source_documents(docs,'Question',selector=lambda _:'[2]',max_chars=1800,required_ids=[1])
    assert '[1]\nTitle:' in text and docs[0].page_content in text
    assert len(text)<=1800

def test_html_table_preserves_rows_columns_and_spanned_labels():
    text=html_text('<table><tr><th>Assay</th><th>Capture</th></tr><tr><td rowspan="2">System A</td><td>Probe</td></tr><tr><td>Poly(A)</td></tr></table>')
    assert '| Assay | Capture |' in text
    assert '| System A | Probe |' in text and '| System A | Poly(A) |' in text


def test_markup_excludes_script_data_and_keeps_unclosed_table_cells():
    text=html_text('<script>Unrelated false assay definition.</script><style>css</style><table><tr><td>Assay Q</td><td>Measured RNA')
    assert 'false assay' not in text and '| Assay Q | Measured RNA |' in text
    assert 'Before script' in html_text('<table><tr><td>Before script<script>unclosed')


def test_second_confirmation_can_reject_a_reviewers_unsupported_correction():
    class Model:
        calls=0
        def invoke(self,prompt):
            self.calls+=1
            if self.calls==1:return SimpleNamespace(content='Accurate statement [7].')
            if self.calls==2:return SimpleNamespace(content=json.dumps({'issues':[{'statement':'Accurate statement [7].',
                'source_id':7,'status':'contradiction','evidence_quote':'The source describes accurate measurement.',
                'replacement':'An unsupported correction [7].'}]}))
            return SimpleNamespace(content='{"decisions":[]}')
    writer=handler(Model());writer.settings_snapshot={'general.enable_fact_checking':True}
    result=writer.analyze_followup('Question',[{'index':7,'abstract':'The source describes accurate measurement.'}],'Draft [7].',0)
    assert result['content']=='Accurate statement [7].'
    assert result['evidence_review']['status']=='review_incomplete'


def test_supported_original_or_different_analysis_prevents_repair():
    from research_verify.evidence_flow import confirm_repairs
    material=format_source_documents([doc(7,'The baseline used 12 neighbors. The recommended workflow used 16 neighbors.')])
    text='Recommended workflow used 16 neighbors [7].'
    issue={'statement':text,'source_id':7,'status':'contradiction',
        'evidence_quote':'The baseline used 12 neighbors.',
        'replacement':'Recommended workflow used 12 neighbors [7].'}
    for supported,same in [(True,True),(False,False),(None,True)]:
        reply=json.dumps({'decisions':[{'candidate_index':0,'original_supported':supported,
            'replacement_supported':True,'same_analysis':same}]})
        model=SimpleNamespace(_invoke_text=lambda *a,**kw:reply)
        out,applied,_=confirm_repairs(model,text,[issue],material,'Question',DISABLED)
        assert out==text and not applied

def test_final_check_reads_the_actual_writer_text_and_repairs_only_quoted_issue():
    class Model:
        def __init__(self):self.prompts=[]
        def invoke(self,prompt):
            self.prompts.append(prompt)
            if len(self.prompts)==1:return SimpleNamespace(content='Study analyzed tissue B [7].')
            if len(self.prompts)==3:return SimpleNamespace(content='{"decisions":[{"candidate_index":0,"original_supported":false,"replacement_supported":true,"same_analysis":true}]}')
            return SimpleNamespace(content='{"issues":[{"statement":"Study analyzed tissue B [7].","source_id":7,"evidence_quote":"Study analyzed tissue A.","replacement":"Study analyzed tissue A [7].","status":"contradiction"}]}')
    model=Model();writer=handler(model);writer.settings_snapshot={'general.enable_fact_checking':True}
    result=writer.analyze_followup('Question',[{'index':7,'abstract':'Study analyzed tissue A.'}],'Unverified draft [7].',0)
    assert result['content']=='Study analyzed tissue A [7].'
    assert 'Study analyzed tissue B [7].' in model.prompts[1]
    assert len(model.prompts)==3


@pytest.mark.parametrize('bad', ['fabricated_quote','unknown_source','new_citation','empty_replacement','uncertain','invalid_statement','boolean_id'])
def test_unusable_review_cannot_rewrite_report(bad):
    material=format_source_documents([doc(7,'The experiment analyzed tissue A specimens.')])
    original='Analyzed tissue B [7].'
    issue={'statement':original,'source_id':7,'status':'contradiction',
           'evidence_quote':'The experiment analyzed tissue A specimens.','replacement':'Analyzed tissue A [7].'}
    if bad=='fabricated_quote':issue['evidence_quote']='A quotation absent from the actual source.'
    if bad=='unknown_source':issue['source_id']=99
    if bad=='new_citation':issue['replacement']='Analyzed tissue A [99].'
    if bad=='empty_replacement':issue['replacement']=''
    if bad=='uncertain':issue['status']='insufficient_evidence'
    if bad=='invalid_statement':issue['statement']={'text':original}
    if bad=='boolean_id':issue['source_id']=True
    result,applied,unresolved=apply_review(original,[issue],material)
    assert result==original and not applied and len(unresolved)==1


def test_repeated_or_overlapping_span_is_not_guessed():
    material=format_source_documents([doc(7,'The experiment analyzed tissue A specimens.')])
    issue={'statement':'Tissue B [7].','source_id':7,'status':'contradiction',
           'evidence_quote':'The experiment analyzed tissue A specimens.','replacement':'Tissue A [7].'}
    text='Tissue B [7]. Again: Tissue B [7].'
    assert apply_review(text,[issue],material)[0]==text


def test_claim_ids_preserve_original_markdown_and_reject_unknown_ids():
    claims={3:{'text':'**Observed tissue B** [7].'}}
    issues=parse_review(json.dumps({'issues':[{'claim_id':3,'evidence_source_id':7},
        {'claim_id':4,'evidence_source_id':7},{'claim_id':True}]}),claims)
    assert issues==[{'claim_id':3,'evidence_source_id':7,'source_id':7,'statement':'**Observed tissue B** [7].'}]


def test_unreviewed_claims_are_not_silently_marked_supported():
    issues=parse_review('{"issues":[{"claim_id":0,"status":"supported"}]}',
        {0:{'text':'First [7].'},1:{'text':'Second [7].'}})
    assert issues==[{'status':'review_claims_unchecked','claim_ids':[1]}]


def test_matching_method_cannot_erase_an_explicit_study_scope_conflict():
    response={'issues':[{'claim_id':0,'status':'supported','evidence_source_id':7,
        'evidence_quote':'Method M was used.', 'replacement':'Method M studied population A [7].',
        'atom_checks':[{'attribute':'method','result':'supported'},
            {'attribute':'population','claim_value':'B','source_value':'A',
             'result':'contradiction','evidence_quote':'We studied population A.'}]}]}
    issues=parse_review(json.dumps(response),{0:{'text':'Method M studied population B [7].'}})
    assert issues[0]['status']=='contradiction' and 'We studied population A.' in issues[0]['evidence_quote']
    out,applied,_=apply_review('Method M studied population B [7].',issues,
        format_source_documents([doc(7,'We studied population A. Method M was used.')]))
    assert applied and out=='Method M studied population A [7].'


def test_true_finding_can_move_when_its_assay_category_is_contradicted():
    from research_verify.evidence_flow import confirm_repairs
    text='## System P\n\nObserved result [7].\n\n## System Q\n\nOther text.'
    material=format_source_documents([doc(7,'All specimens were measured with system Q.')])
    issue={'statement':'Observed result [7].','replacement':'Observed result using system Q [7].',
        'source_id':7,'status':'contradiction','evidence_quote':'All specimens were measured with system Q.',
        'destination_heading':'## System Q'}
    reply=json.dumps({'decisions':[{'candidate_index':0,'original_supported':True,
        'replacement_supported':True,'same_analysis':True,'placement_supported':False}]})
    out,applied,_=confirm_repairs(SimpleNamespace(_invoke_text=lambda *a,**kw:reply),
        text,[issue],material,'Question',DISABLED)
    assert applied and out.index('Observed result using system Q')>out.index('## System Q')


def test_same_or_parent_heading_does_not_move_a_correct_statement():
    text='## Group A\n\n### Analysis\n\nObserved result [7].\n\n### Next\n\nOther text.'
    material=format_source_documents([doc(7,'The observed result was measured.')])
    issue={'statement':'Observed result [7].','replacement':'Observed result [7].',
        'source_id':7,'status':'contradiction','evidence_quote':'The observed result was measured.'}
    for heading in ['## Group A','Analysis']:
        out,applied,_=apply_review(text,[{**issue,'destination_heading':heading}],material)
        assert out==text and not applied


def test_review_groups_preserve_uncited_assertions_and_table_context():
    text='## Group A\n\nA categorical statement.\n\n| Measure | Finding |\n| --- | --- |\n| A | Observed [7]. |\n'
    groups=review_claim_groups(text,[doc(7,'Evidence.')],[{'index':7}],'Question',60000)
    claims=[c for g in groups for c in g.values()]
    assert any(c['text']=='A categorical statement.' and not c['source_ids'] for c in claims)
    row=next(c for c in claims if c['source_ids'])
    assert row['table_context']=='| Measure | Finding |' and row['section_context']==['## Group A']


def test_owned_full_text_can_be_used_after_network_budget_is_exhausted():
    class Fetch:
        remaining=0
        def article(self,_):raise AssertionError('Existing full text must be reused')
    sources=[{'index':7,'content_type':'full_text','content':'Already retrieved primary evidence.'}]
    result=supplement([{'status':'insufficient_evidence','source_id':7,'request':{'kind':'article'}}],
        sources,Fetch(),register=None,trace=DISABLED)
    assert result==[7] and sources[0]['fetched_content']=='Already retrieved primary evidence.'


def test_review_call_budget_keeps_report_when_confirmation_is_unavailable():
    class Model:
        calls=0
        def invoke(self,prompt):
            self.calls+=1
            if self.calls==1:return SimpleNamespace(content='Original statement [7].')
            return SimpleNamespace(content=json.dumps({'issues':[{'statement':'Original statement [7].',
                'replacement':'A proposed change [7].','source_id':7,'status':'contradiction',
                'evidence_quote':'The original supporting material is available.'}]}))
    writer=handler(Model());writer.settings_snapshot={'general.enable_fact_checking':True,'citation.max_review_calls':1}
    result=writer.analyze_followup('Question',[{'index':7,'abstract':'The original supporting material is available.'}],'Draft [7].',0)
    assert result['content']=='Original statement [7].' and writer.llm.calls==2
    assert result['evidence_review']['status']=='review_incomplete'


def test_wrong_section_entry_can_move_without_rewriting_other_content():
    material=format_source_documents([doc(7,'The experiment used measurement system Q on all specimens.')])
    text='## System P\n\nStudy result [7].\n\n## System Q\n\nOther content stays.'
    issue={'statement':'Study result [7].','source_id':7,'status':'contradiction',
           'evidence_quote':'The experiment used measurement system Q on all specimens.',
           'replacement':'Study result with system Q [7].','destination_heading':'## System Q'}
    out,applied,_=apply_review(text,[issue],material)
    assert out.index('Study result with system Q')>out.index('## System Q')
    assert 'Other content stays.' in out and len(applied)==1


def test_source_budget_overflow_splits_draft_sections_with_evidence_intact():
    docs=[doc(1,'Source one original evidence. '*18),doc(2,'Source two original evidence. '*18)]
    sources=[{'index':1},{'index':2}]
    draft='## First\nObserved first [1].\n\n## Second\nObserved second [2].'
    batches=writing_batches(draft,docs,sources,'Question',budget=2000)
    assert len(batches)==2 and 'Second' not in batches[0]
    for batch in batches:
        ids=[i for i in [1,2] if f'[{i}]' in batch]
        text=format_source_documents(docs,'Question',selector=lambda _:'[1,2]',max_chars=2000,required_ids=ids)
        assert all(f'[{i}]\nTitle:' in text for i in ids) and len(text)<=2000


def test_version_lookup_keeps_text_versions_separate_and_reuses_existing_publication():
    class Fetch:
        def record(self,_):raise AssertionError('Existing publication must not be fetched again')
    records=[{'index':1,'pmid':'100','doi':'10.1000/pre','abstract':'Preprint finding.',
        'publication_types':['Preprint'],'related_articles':[{'relation_type':'update_in','pmid':'200'}]},
        {'index':2,'pmid':'200','doi':'10.1000/pub','abstract':'Published finding.'}]
    resolve_versions(records,Fetch())
    assert len(records)==2 and records[0]['doi']=='10.1000/pre'
    assert records[0]['abstract']=='Preprint finding.' and records[1]['abstract']=='Published finding.'
    assert records[0]['publication_versions'][0]['index']==2


def test_linked_publication_gets_its_own_stable_index_and_metadata():
    class Fetch:
        calls=0
        def record(self,_):
            self.calls+=1
            return {'id':'200','source':'MED','doi':'10.1000/pub','title':'Published study',
                    'abstractText':'Published evidence differs from the earlier draft.',
                    'pubTypeList':{'pubType':['Journal Article']}}
    fetch=Fetch();records=[{'index':1,'pmid':'100','abstract':'Earlier evidence.',
        'related_articles':[{'relation_type':'update_in','pmid':'200'}]}]
    resolve_versions(records,fetch,register=lambda source,engine:77)
    resolve_versions(records,fetch)
    assert fetch.calls==1 and records[1]['index']=='77'
    writer=handler(SimpleNamespace())
    material=format_source_documents(writer._create_documents(records))
    assert 'Related version source index: 77' in material and 'Publication relation: update_in' in material
    assert 'Published evidence differs' in material and 'Earlier evidence.' in material


def test_failed_version_lookup_retains_original_evidence_and_explicit_status():
    class Fetch:
        def record(self,_):raise TimeoutError()
    records=[{'index':1,'doi':'10.1000/pre','abstract':'Original preprint.',
              'related_articles':[{'relation_type':'update_in','pmid':'200'}]}]
    resolve_versions(records,Fetch())
    assert len(records)==1 and records[0]['abstract']=='Original preprint.'
    assert 'not retrieved' in records[0]['version_resolution']


def test_version_repair_requires_the_cited_papers_own_explicit_link():
    docs=[doc(1,'Original unrelated article.'),doc(2,'Earlier version of the method.'),
          doc(3,'Published method identifies spatial patterns.')]
    docs[1].metadata['publication_versions']=[{'index':3,'relation_type':'update_in'}]
    material=format_source_documents(docs)
    base={'source_id':3,'status':'version_update','evidence_quote':'Published method identifies spatial patterns.',
          'replacement':'The method identifies spatial patterns [3].'}
    wrong='The method identifies spatial patterns [1].'
    assert apply_review(wrong,[{**base,'statement':wrong}],material)[0]==wrong
    right='The method identifies spatial patterns [2].'
    assert apply_review(right,[{**base,'statement':right}],material)[0]==base['replacement']


def test_linked_version_quote_and_replacement_resolve_reviewers_old_source_id():
    docs=[doc(2,'The earlier method identifies spatial patterns.'),doc(3,'Published method identifies spatial patterns.')]
    docs[0].metadata['publication_versions']=[{'index':3,'relation_type':'update_in'}]
    original='The method identifies spatial patterns [2].'
    issue={'statement':original,'source_id':2,'status':'version_update',
        'evidence_quote':'Published method identifies spatial patterns.',
        'replacement':'The method identifies spatial patterns [3].'}
    out,applied,_=apply_review(original,[issue],format_source_documents(docs))
    assert out==issue['replacement'] and applied[0]['source_id']==3


def test_explicit_versions_propose_comparison_even_when_reviewer_omits_version_issue():
    from research_verify.evidence_flow import version_candidates
    sources=[{'index':2,'publication_versions':[{'index':3}]},{'index':3}]
    docs=[doc(2,'Earlier finding.'),doc(3,'The published method identifies patterns.')]
    docs[0].metadata['publication_versions']=[{'index':3}]
    material=format_source_documents(docs)
    claims={0:{'text':'The method identifies patterns [2][3].'}}
    proposed=version_candidates(claims,sources,material)
    assert proposed[0]['replacement']=='The method identifies patterns [3].'
    # A proposed version change is still rejected without an independent verdict.
    from research_verify.evidence_flow import confirm_repairs
    out,applied,_=confirm_repairs(SimpleNamespace(_invoke_text=lambda *a,**kw:'{"decisions":[]}'),
        claims[0]['text'],proposed,material,'Question',DISABLED)
    assert not applied and out==claims[0]['text']
    linked=version_candidates({0:{'text':'Result [2](https://example.org/preprint).'}},sources,material)
    assert linked[0]['replacement']=='Result [3].'


def test_only_located_quotes_reach_independent_confirmation():
    from research_verify.evidence_flow import confirm_repairs
    material=format_source_documents([doc(7,'We measured population A with method M.')])
    issue={'statement':'Measured population B [7].','replacement':'Measured population A [7].',
        'status':'contradiction','source_id':7,
        'evidence_quote':['We measured population A...', 'We measured population A with method M.']}
    def invoke(prompt,**kwargs):
        assert 'We measured population A...' not in prompt
        return '{"decisions":[{"candidate_index":0,"original_supported":false,"replacement_supported":true,"same_analysis":true}]}'
    out,applied,_=confirm_repairs(SimpleNamespace(_invoke_text=invoke),issue['statement'],[issue],material,'Question',DISABLED)
    assert out==issue['replacement'] and applied[0]['unlocated_quote_count']==1


def test_failed_article_retrieval_is_not_retried_for_every_claim():
    fetch=EvidenceFetcher(get=lambda *a,**kw:None)
    calls=[]
    def fail(source):calls.append(source);raise TimeoutError()
    fetch._article=fail
    with pytest.raises(TimeoutError):fetch.article({'pmid':'123'})
    assert fetch.article({'pmid':'123'}) is None and len(calls)==1


def test_fetch_budget_cannot_make_unbounded_requests_or_read_unbounded_body(tmp_path,monkeypatch):
    monkeypatch.setenv('LDR_DATA_DIR',str(tmp_path))
    calls=[]
    class Response:
        closed=False
        def raise_for_status(self):pass
        def iter_content(self,_):yield b'x'*100
        def close(self):self.closed=True
    response=Response()
    def get(*args,**kwargs):calls.append(kwargs);return response
    fetch=EvidenceFetcher(get=get,requests=1)
    with pytest.raises(TimeoutError):fetch.read('https://example.org',limit=10)
    assert response.closed
    with pytest.raises(TimeoutError):fetch.read('https://example.org')
    assert len(calls)==1 and calls[0]['timeout'][1]<=5


def test_stream_callback_receives_only_the_final_repaired_text():
    class Model:
        calls=0
        def invoke(self,_):
            self.calls+=1
            return SimpleNamespace(content=['Wrong object [7].',json.dumps({'issues':[{'statement':'Wrong object [7].',
                'source_id':7,'status':'contradiction','evidence_quote':'The measured object was object A.',
                'replacement':'Object A was measured [7].'}]}),'{"decisions":[{"candidate_index":0,"original_supported":false,"replacement_supported":true,"same_analysis":true}]}'][self.calls-1])
        def stream(self,_):raise AssertionError('Pre-review stream must be buffered')
    writer=handler(Model());writer.settings_snapshot={'general.enable_fact_checking':True}
    seen=[];writer.stream_callback=seen.append
    result=writer.analyze_followup('Question',[{'index':7,'abstract':'The measured object was object A.'}],'Draft [7].',0)
    assert seen==[result['content']]==['Object A was measured [7].']


def test_insufficient_evidence_can_be_supplemented_once_then_rechecked():
    class Fetch:
        remaining=4
        def article(self,source):self.remaining-=1;return 'Detailed methods used measurement system Q for all samples.'
    class Model:
        calls=0
        def invoke(self,prompt):
            self.calls+=1
            if self.calls==1:return SimpleNamespace(content='Used system P [7].')
            if self.calls==2:return SimpleNamespace(content=json.dumps({'issues':[{'statement':'Used system P [7].',
                'source_id':7,'status':'insufficient_evidence','request':{'kind':'article'}}]}))
            if self.calls==3:
                assert 'Detailed methods used measurement system Q' in prompt
                return SimpleNamespace(content=json.dumps({'issues':[{'statement':'Used system P [7].','source_id':7,
                    'status':'contradiction','evidence_quote':'Detailed methods used measurement system Q for all samples.',
                    'replacement':'Used system Q [7].'}]}))
            return SimpleNamespace(content='{"decisions":[{"candidate_index":0,"original_supported":false,"replacement_supported":true,"same_analysis":true}]}')
    writer=handler(Model());writer.evidence_fetcher=Fetch();writer.settings_snapshot={'general.enable_fact_checking':True}
    sources=[{'index':7,'abstract':'We studied the distribution of measurements.'}]
    result=writer.analyze_followup('Question',sources,'Draft [7].',0)
    assert result['content']=='Used system Q [7].' and writer.llm.calls==4
    assert 'fetched_content' in sources[0]
