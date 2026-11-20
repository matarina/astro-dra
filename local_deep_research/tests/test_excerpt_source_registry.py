from types import SimpleNamespace

from research_verify.generation import format_source_documents
from research_verify.evidence_flow import visible_texts,visible_headers


def document(index):
    text=('Background material with no requested outcome.\n\n'*3000+
          'The measured endpoint did not improve in the treatment group.\n\n')
    return SimpleNamespace(page_content=text,metadata=dict(index=index,title='Actual study',source='https://example.org/'+str(index)))


def test_excerpt_registry_is_present_without_optional_trace_and_matches_supplied_bytes():
    doc=document(17);shown=format_source_documents([doc],'measured endpoint',max_chars=20000,required_ids={17})
    assert set(shown.views)=={17}
    view=shown.views[17]
    assert view['block']in shown and view['text']in shown
    assert view['text']!=doc.page_content and 'did not improve'in view['text']
    assert visible_texts(shown)[17]==view['text']and visible_headers(shown)[17]==view['metadata']
    scope=[];with_scope=format_source_documents([doc],'measured endpoint',max_chars=20000,required_ids={17},reading_scope=scope)
    assert shown==with_scope and shown.views==with_scope.views
    assert scope==[view]


def test_selection_registry_contains_only_selected_original_source_ids():
    docs=[document(i)for i in [4,17,31,66]]
    receipts=[]
    shown=format_source_documents(docs,'measured endpoint',max_chars=1800,
        selector=lambda prompt:'[31,17,4,66]',selection_receipts=receipts)
    selected=set(receipts[-1]['selected_ids'])
    assert selected and selected!={4,17,31,66}
    assert set(shown.views)==selected
    assert all(v['block']in shown for v in shown.views.values())
