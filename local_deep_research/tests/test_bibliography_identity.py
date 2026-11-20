from research_verify.bibliography_identity import bibliography_entries,identifiers,match_identifiers


def test_bibliography_source_mapping_uses_ids_not_report_numbers_or_journal_names():
    report='A statement [8].\n\nSources\n\n[8] Example title\nURL: https://pubmed.ncbi.nlm.nih.gov/12345/\nDOI: 10.1234/Example\n'
    entry=bibliography_entries(report)[0]
    assert report[entry['start']:entry['end']]==entry['text']
    records={'1':{'pmid':'12345','doi':'10.1234/example','journal':'Other Journal'},
             '8':{'pmid':'98765','journal':'Example Journal'}}
    result=match_identifiers(entry,records)
    assert result['status']=='one_record_match' and result['matches'][0]['record_key']=='1'


def test_conflicting_ids_or_multiple_values_prevent_unique_binding():
    entry={'doi':'10.1234/example','pmid':'12345'}
    result=match_identifiers(entry,{'r':{'doi':'10.1234/example','pmid':'98765'}})
    assert result['status']=='identifier_conflict' and not result['matches']
    entry={'text':'DOI: 10.1234/example\nDOI: 10.1234/other\n'}
    assert match_identifiers(entry,{'r':{'doi':'10.1234/example'}})['status']=='identifier_conflict'


def test_title_similarity_and_truncated_or_invented_ids_do_not_bind():
    assert match_identifiers({'title':'Same title'},{'r':{'title':'Same title'}})['status']=='no_identifier_match'
    assert identifiers({'url':'https://example.org/12345','pmid':'not-a-number'})=={}
    assert identifiers({'url':'https://europepmc.org/article/MED/12345'})=={'pmid':['12345']}
    assert identifiers({'url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/'})=={'pmcid':['PMC12345']}


def test_duplicate_bibliography_numbers_are_not_silently_merged():
    report='Sources\n\n[4] A\nDOI: 10.1234/a\n[4] B\nDOI: 10.1234/b\n'
    entries=bibliography_entries(report)
    assert len(entries)==2 and not any(e['source_id_unique'] for e in entries)
    assert match_identifiers(entries[0],{'r':{'doi':'10.1234/a'}})['status']=='nonunique_bibliography_source_id'
