import copy
from research_verify.question_routing import route_questions


def question():return [dict(question_id='q',claim_id='c',source_id=2,question='Which sample and assay?')]


def test_exact_pair_routes_to_body_alias_without_renumbering_or_mutation():
    sources=[dict(index=1,pmid='123',doi='10.1234/a',fetched_content='original body'),dict(index=2,pmid='123',doi='10.1234/a')]
    before=copy.deepcopy(sources);r=route_questions(question(),sources)
    assert {x['reader_source_id']for x in r}=={'1','2'}
    assert all(x['original_source_id']=='2'and x['semantic_verdict']is None for x in r)
    assert sources==before


def test_title_only_one_identifier_and_conflicting_ids_do_not_route():
    for sources in [
        [dict(index=1,title='same'),dict(index=2,title='same')],
        [dict(index=1,pmid='123',doi='10.1234/a'),dict(index=2,pmid='123',doi='10.1234/b')],
        [dict(index=1,pmid='123',doi='10.1234/a'),dict(index=2,doi='10.1234/a')],
        [dict(index=1,pmid='123',doi='10.1234/a',pmcid='PMC1'),dict(index=2,pmid='123',doi='10.1234/a',pmcid='PMC2')],
        [dict(index=1,pmid='123',doi='10.1234/a',pmcid='PMC1'),dict(index=2,pmid='123',doi='10.1234/a'),dict(index=3,pmid='123',doi='10.1234/a',pmcid='PMC2')],
    ]:
        assert [x['reader_source_id']for x in route_questions(question(),sources)]==['2']
