"""Offline acquisition-contract audit with identity-bound cached primary bodies.

Produces a NEW sourcepack; never mutates its inputs, calls a model or fetches
the network. Scope correction changes actual source views too, not just labels.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path

from research_verify.generation import source_material
from research_verify.pmc_identity import article_text, _doi
from research_verify.source_evidence import ArticleEvidenceClient


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-manifest', type=Path, required=True)
    p.add_argument('--bindings', type=Path, required=True)
    p.add_argument('--old-generation', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(exist_ok=False)
    manifest = json.loads(a.case_manifest.read_text())
    case = manifest['cases'][0]
    src = Path(case['source'])
    assert sha(src) == case['source_sha256']
    old = json.loads(src.read_text())
    new = copy.deepcopy(old)
    by_id = {str(s['index']): s for s in new}
    assert len(by_id) == len(new)
    bindings = json.loads(a.bindings.read_text())['bindings']
    input_files = [a.case_manifest, a.bindings, src, Path(case['draft']), a.old_generation,
                   Path(__file__), *Path('local_deep_research/research_verify').glob('*.py'),
                   *[Path(b['xml_path']) for b in bindings]]
    frozen = {str(f): sha(f) for f in input_files}
    write(a.out_dir / 'prestart-freeze.json', frozen)
    for f in input_files:
        if str(f).startswith(('scripts/', 'local_deep_research/')):
            target = a.out_dir / 'code' / f
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    # Load only the historical pure formatter, never the old module's imports.
    tree = ast.parse(a.old_generation.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'source_material')
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(a.old_generation), 'exec'), namespace)
    old_material = namespace['source_material']
    bodies = {}
    for b in bindings:
        source = by_id[b['source_id']]
        own = b['own_article_ids']
        assert str(source['pmid']) == own['pmid'] and _doi(source['doi']) == _doi(own['doi'])
        xml = Path(b['xml_path'])
        assert sha(xml) == b['xml_sha256']
        body = article_text(xml.read_text(), {'pmcid': own['pmcid'], 'doi': own['doi']},
                            pmid=own['pmid'], require_body=True)
        assert body and len(body) == b['body_chars'] and digest(body) == b['body_sha256']
        assert source['fetched_content'] == body
        bodies[b['source_id']] = body

    class CacheOnly:
        def __init__(self):
            self.calls = []

        def article(self, source):
            self.calls.append(str(source['index']))
            return bodies[str(source['index'])]

        def web(self, *args, **kwargs):
            raise AssertionError('Network/page fallback forbidden in offline cached-body audit')

    fetcher = CacheOnly()
    client = ArticleEvidenceClient(fetcher=fetcher)
    observations = []
    for sid, body in bodies.items():
        source = by_id[sid]
        before = copy.deepcopy(source)
        update = client.fetch(source)
        assert update and update['body'] == body
        source.update(update)
        old_view, old_basis = old_material(before)
        new_view, new_basis = source_material(source)
        assert body in old_view and new_view == body
        # Reproduce the separate formatter defect on the same REAL body.
        variants = []
        for kind in ['full_text', 'fulltext', 'full-text', 'body']:
            body_only = {'abstract': before['abstract'], 'body': body, 'content_type': kind}
            historical, historical_basis = old_material(body_only)
            repaired, repaired_basis = source_material(body_only)
            assert repaired == body and historical == before['abstract']
            variants.append(dict(content_type=kind, old_body_exposed=body in historical,
                                 new_body_exposed=body in repaired, old_basis=historical_basis,
                                 new_basis=repaired_basis))
        changed = sorted(k for k in source if source.get(k) != before.get(k))
        assert all(source[k] == before[k] for k in before if k not in update)
        observations.append(dict(source_id=sid, body_sha256=digest(body), body_chars=len(body),
                                 old_basis=old_basis, new_basis=new_basis,
                                 old_view_chars=len(old_view), new_view_chars=len(new_view),
                                 old_view_sha256=digest(old_view), new_view_sha256=digest(new_view),
                                 body_already_exposed_before=True,
                                 original_abstract_field_preserved=source['abstract'] == before['abstract'],
                                 original_abstract_contiguous_in_new_view=source['abstract'] in new_view,
                                 changed_fields=changed, body_only_variants=variants))
    unchanged = [str(s['index']) for s in old if str(s['index']) not in bodies]
    assert all(by_id[str(s['index'])] == s for s in old if str(s['index']) in unchanged)
    write(a.out_dir / 'sources.json', new)
    case['source'] = str(a.out_dir / 'sources.json')
    case['source_sha256'] = sha(a.out_dir / 'sources.json')
    write(a.out_dir / 'case-manifest.json', manifest)
    assert all(sha(Path(f)) == h for f, h in frozen.items())
    receipt = dict(scope='Offline real-cache acquisition/formatter contract audit, not report-quality assessment',
                   source_records=len(new), body_sources=len(bodies), unchanged_source_ids=unchanged,
                   observations=observations, cached_article_calls=fetcher.calls,
                   input_hashes_unchanged=True, new_sourcepack_sha256=case['source_sha256'],
                   model_calls=0, network_reads=0, independent_correction_credit=0,
                   label_only_ablation=False,
                   limit='Correct contract replaces combined canonical abstract/page view with acquired article text. '
                         'Original abstract remains in source record but may not occur verbatim in selected view. '
                         'No full published-paper/supplement completeness or semantic verdict follows.')
    write(a.out_dir / 'receipt.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'observations'}))


if __name__ == '__main__':
    main()
