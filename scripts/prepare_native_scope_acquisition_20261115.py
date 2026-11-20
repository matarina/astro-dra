"""Preserve native quotation diagnoses and identity-bound acquisition inputs."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from research_verify.pmc_identity import article_text
from scripts.audit_material_exposure_20261115 import extracted_review_material


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def display_map(text):
    """Diagnostic projection only; retain signs/case and original intervals.

    Flattening explicit display markers can erase scientific notation. A
    projected match is only a candidate location, never an accepted quotation
    or support verdict. This function has no production/repair caller.
    """
    chars, coordinates = [], []
    pos = 0
    for match in re.finditer(r'\[(?:superscript|subscript):([^\[\]]+)\]', text):
        for i in range(pos, match.start()):
            if not text[i].isspace():
                chars.append(text[i]); coordinates.append((i, i+1))
        for char in match[1]:
            if not char.isspace():
                chars.append(char); coordinates.append(match.span())
        pos = match.end()
    for i in range(pos, len(text)):
        if not text[i].isspace():
            chars.append(text[i]); coordinates.append((i, i+1))
    return ''.join(chars), coordinates


def display_candidate(hint, text):
    projected, coordinates = display_map(text)
    needle, _ = display_map(hint)
    if len(needle) < 20:
        return dict(status='short_nonliteral_hint_not_resolved')
    positions = [m.start() for m in re.finditer('(?=' + re.escape(needle) + ')', projected)]
    if len(positions) != 1:
        return dict(status='ambiguous_or_not_located', occurrences=len(positions))
    a, b = coordinates[positions[0]][0], coordinates[positions[0]+len(needle)-1][1]
    return dict(status='nonverbatim_display_candidate_only', start=a, end=b,
                original_text=text[a:b], hint_is_verbatim=hint == text[a:b], semantic_support='not_assessed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args(); a.out_dir.mkdir(exist_ok=False)
    root = Path('evaluation/frontier-strategy-20261113')
    case_path = root / 'immune-questioned-fact-inputs-20261115-v1/case-manifest.json'
    case = json.loads(case_path.read_text())['cases'][0]
    source_path = Path(case['source'])
    assert sha(source_path) == case['source_sha256']
    sources = json.loads(source_path.read_text())
    source, = [s for s in sources if str(s['index']) == '19']
    xml_path = root / 'native-source19-primary-retrieval-20261115-v2/article.xml'
    retrieval = json.loads((xml_path.parent / 'result.json').read_text())
    assert sha(xml_path) == retrieval['sha256'] and retrieval['http_status'] == 200
    tree = ET.fromstring(xml_path.read_text())
    meta = tree.find('.//article-meta')
    ids = {e.get('pub-id-type'): ''.join(e.itertext()).strip() for e in meta.findall('article-id')}
    assert ids['pmid'] == source['pmid'] and ids['doi'] == source['doi'] and ids['pmcid'] == source['pmcid']
    body = article_text(xml_path.read_text(), {'pmcid': source['pmcid'], 'doi': source['doi']},
                        pmid=source['pmid'], require_body=True)
    assert body
    (a.out_dir / 'acquired-article-text.txt').write_text(body)
    probe = root / 'uncited-discovery-probe-model-20261115-v2/attempt'
    quote_path = root / 'uncited-discovery-complete-native-audit-20261115-v1/literal-native-quote-provenance.json'
    rows = json.loads(quote_path.read_text())
    material = {group: extracted_review_material((probe / f'group-{group}/prompt.txt').read_text(), range(1, 21)) for group in [8, 9]}
    diagnosis = []
    for row in rows:
        view = material[row['group']].views[row['source_id']]
        hint = row['quote']
        if row['exact_in_actual_source_block']:
            location = dict(status='literal_source_block_occurrence_only', semantic_support='not_assessed')
        else:
            location = display_candidate(hint, view['text'])
        diagnosis.append(dict(**row, location=location))
    write(a.out_dir / 'display-location-diagnosis.json', diagnosis)
    # Explicit counterexamples: projection does not equate polarity, alter
    # the source, select another study, or turn scientific notation into truth.
    assert display_candidate('The cells were CD3 + and CD4 − selected.',
        'The cells were CD3 [superscript:+] and CD4 [superscript:−] selected.')['status'] == 'nonverbatim_display_candidate_only'
    assert display_candidate('The cells were CD3 + and CD4 − selected.',
        'The cells were CD3 [superscript:−] and CD4 [superscript:+] selected.')['status'] == 'ambiguous_or_not_located'
    old_text = source['abstract']
    old_prompt = material[9].views[19]['text']
    assert old_text == old_prompt and 'CD3' not in old_prompt
    windows = []
    cursor = 0
    for paragraph in body.split('\n\n'):
        if 'CD3' in paragraph:
            windows.append(dict(start=cursor, end=cursor+len(paragraph), text=paragraph))
        cursor += len(paragraph)+2
    assert windows and all(body[r['start']:r['end']] == r['text'] for r in windows)
    write(a.out_dir / 'new-acquisition-scope.json', dict(source_id=19, own_article_ids=ids,
        xml_sha256=sha(xml_path), acquired_chars=len(body), acquired_sha256=sha(a.out_dir / 'acquired-article-text.txt'),
        original_abstract_chars=len(old_text), original_abstract_sha256=hashlib.sha256(old_text.encode()).hexdigest(),
        new_body_was_in_previous_prompt=False, original_view_contains_CD3=False,
        acquired_body_CD3_occurrences=body.count('CD3'), original_contexts=windows,
        provisional_finding='New primary methods text reports CD3-positive T-cell identification. Prior supplied abstract does not.',
        independent_report_adjudication=False, new_independent_correction_credit=0))
    common = dict(source_id=19, title=source['title'], doi=source['doi'], pmid=source['pmid'],
        scope='Actual supplied source text; additional own-article text only when present; published-paper completeness unconfirmed',
        evidence_questions=[])
    variants = [('abstract', old_text), ('acquired', old_text + '\n\nADDITIONAL IDENTITY-BOUND ACQUIRED ARTICLE TEXT:\n' + body)]
    cases = []
    for key, text in variants:
        path = a.out_dir / (key + '-views.json')
        write(path, [{**common, 'text': text}])
        cases.append(dict(case_id=key, query=case['query'], views_path=str(path), views_sha256=sha(path)))
    write(a.out_dir / 'cases.json', dict(cases=cases, scope='One known paper/task; acquisition-only source-reader diagnostic, no old report/verdict/expected answer in prompts.'))
    files = [case_path, source_path, xml_path, xml_path.parent / 'result.json', quote_path,
             probe / 'group-8/prompt.txt', probe / 'group-9/prompt.txt',
             Path(__file__).resolve().relative_to(Path.cwd()), *Path('local_deep_research/research_verify').glob('*.py')]
    write(a.out_dir / 'input-freeze.json', {str(f): sha(f) for f in files})
    for f in files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            dest = a.out_dir / 'code' / f; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(f.read_bytes())
    print(json.dumps(dict(display_candidates=sum(r['location']['status']=='nonverbatim_display_candidate_only' for r in diagnosis),
        body_chars=len(body), model_calls=0, new_independent_correction_credit=0)))


if __name__ == '__main__':
    main()
