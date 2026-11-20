import hashlib

from research_verify.article_structure import article_structure_index, attach_article_structure


def unit(sid, uid, text):
    return dict(material_id='original',source_id=sid,unit_id=uid,kind='text',text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest())


XML = ('<article><front><article-meta><article-id pub-id-type="pmid">123</article-id>'
       '<article-id pub-id-type="pmc">PMC456</article-id><abstract><p>Summary.</p></abstract>'
       '</article-meta></front><body><sec id="m"><title>Methods</title><p>Shared words.</p>'
       '<fig id="f"><caption><title>Caption title</title><p>Caption procedure.</p></caption></fig>'
       '<sub-article><body><p>Foreign procedure.</p></body></sub-article></sec></body>'
       '<back><ref-list><ref id="r"><label>1.</label><mixed-citation>Shared words.</mixed-citation>'
       '</ref><ref><mixed-citation>Other paper title.</mixed-citation></ref></ref-list>'
       '<sec><title>Data availability</title><p>Repository locator.</p></sec></back></article>')


def test_exact_locations_preserve_bibliographic_vs_body_ambiguity_and_every_original_byte():
    index = article_structure_index(XML,{'pmcid':'PMC456'},'123')
    units = [unit(7,0,'Shared words.'),unit(7,1,'Other paper title.'),unit(8,0,'Other paper title.')]
    rows = attach_article_structure(units,{7:index})
    assert rows[0]['original_structure']['status']=='ambiguous_exact_nodes'
    assert rows[0]['original_structure']['possible_scopes']==['bibliographic_reference','body']
    assert rows[1]['original_structure']['possible_scopes']==['bibliographic_reference']
    assert rows[2]['original_structure']['status']=='no_identity_bound_xml'
    assert all({k:v for k,v in r.items() if k!='original_structure'}==u for r,u in zip(rows,units))


def test_caption_nodes_keep_container_and_original_section_no_image_reading():
    index = article_structure_index(XML,{'pmcid':'PMC456'},'123')
    row, = attach_article_structure([unit(7,0,'Caption procedure.')],{7:index})
    assert row['original_structure']['possible_scopes']==['body']
    assert any([c['kind'] for c in loc['containers']]==['fig','caption']
               and loc['section_path'][0]['title']=='Methods' for loc in row['original_structure']['locations'])
    assert index['visual_content_status']=='not_inspected_or_transcribed'


def test_foreign_article_back_matter_and_abstract_do_not_acquire_body_scope():
    index = article_structure_index(XML,{'pmcid':'PMC456'},'123')
    rows = attach_article_structure([unit(7,i,t) for i,t in enumerate(
        ['Foreign procedure.','Repository locator.','Summary.','Unseen paraphrase.'])],{7:index})
    assert [r['original_structure']['possible_scopes'] for r in rows]==[
        ['other_article'],['back_matter'],['abstract'],[]]
    assert rows[-1]['original_structure']['status']=='no_exact_node'
    assert article_structure_index(XML,{'pmcid':'PMC999'},'123') is None


def test_namespaced_structure_and_duplicate_paths_remain_explicit():
    index=article_structure_index(XML.replace('<article>','<article xmlns="urn:jats">'),{'pmcid':'PMC456'},'123')
    row,=attach_article_structure([unit(7,0,'Shared words.')],{7:index})
    paths=[loc['xml_path'] for loc in row['original_structure']['locations']]
    assert len(paths)==len(set(paths)) and len(paths)>1


def test_scope_projection_keeps_all_candidates_and_units_without_full_location_duplication():
    index=article_structure_index(XML,{'pmcid':'PMC456'},'123')
    units=[unit(7,0,'Shared words.')]
    full,=attach_article_structure(units,{7:index})
    compact,=attach_article_structure(units,{7:index},location_detail='scopes')
    assert compact['text']==units[0]['text'] and compact['text_sha256']==units[0]['text_sha256']
    assert compact['original_structure']['possible_scopes']==full['original_structure']['possible_scopes']
    assert compact['original_structure']['match_count']==full['original_structure']['match_count']
    assert 'locations' not in compact['original_structure']
    assert compact['original_structure']['location_detail']=='scopes_only_full_locations_in_index'
