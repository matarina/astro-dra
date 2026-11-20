"""Prepare a known-task whole-source reading packet; no model or verdict."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research_verify.article_context import article_context_index, attach_article_context
from research_verify.canonical_fields import source_units
from research_verify.source_explanations import source_explanation_jobs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-manifest', type=Path, required=True)
    parser.add_argument('--source-id', type=int, required=True)
    parser.add_argument('--article-xml', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--include-structure', action='store_true')
    parser.add_argument('--structure-scopes-only', action='store_true')
    parser.add_argument('--compact-context', action='store_true')
    args = parser.parse_args()
    case, = json.loads(args.case_manifest.read_text())['cases']
    pack = Path(case['source'])
    assert sha(pack) == case['source_sha256']
    assert hashlib.sha256(case['query'].encode()).hexdigest() == case['query_sha256']
    record, = [r for r in json.loads(pack.read_text()) if str(r['index']) == str(args.source_id)]
    text = record.get('fetched_content')
    assert isinstance(text, str) and text.strip(), 'No acquired complete text to prepare'
    args.out_dir.mkdir(exist_ok=False)
    paths = [Path(__file__), args.case_manifest, pack, args.article_xml,
             *Path('local_deep_research/research_verify').glob('*.py')]
    frozen = {str(p): sha(p) for p in paths}
    write(args.out_dir/'prestart-freeze.json', frozen)
    for p in paths:
        if str(p).startswith(('scripts/', 'local_deep_research/')):
            target = args.out_dir/'code'/p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    index = article_context_index(args.article_xml.read_bytes(), record, record.get('pmid'))
    assert index is not None, 'Own article identity does not match'
    metadata = json.dumps({k:record.get(k) for k in ['title','pmid','pmcid','doi','journal','pubdate']}, ensure_ascii=False)
    # Use the canonical splitter's structured source registry, not delimiter regex.
    class Material(str):
        pass
    material = Material('')
    material.views = {args.source_id: dict(text=text, metadata=metadata)}
    digest = hashlib.sha256(text.encode()).hexdigest()
    original = [{**u, 'material_id':'acquired_'+digest} for u in source_units(material,{args.source_id})]
    enriched = attach_article_context(original,{args.source_id:index})
    assert all({k:v for k,v in row.items() if k!='original_context'} == old for row,old in zip(enriched,original))
    if args.include_structure:
        from research_verify.article_structure import article_structure_index, attach_article_structure
        structure = article_structure_index(args.article_xml.read_bytes(),record,record.get('pmid'))
        assert structure is not None
        before = enriched
        enriched = attach_article_structure(before,{args.source_id:structure},
            location_detail='scopes' if args.structure_scopes_only else 'full')
        assert all({k:v for k,v in row.items() if k!='original_structure'} == old for row,old in zip(enriched,before))
        write(args.out_dir/'article-structure-index.json',structure)
    job, = source_explanation_jobs(case['query'],enriched,max_prompt_chars=500000)
    if args.compact_context:
        from research_verify.source_explanations import compact_context_prompt
        job['prompt'], compact = compact_context_prompt(case['query'],enriched)
        write(args.out_dir/'compact-context.json',compact)
    (args.out_dir/'original-question.txt').write_text(case['query'])
    (args.out_dir/'acquired-text.txt').write_text(text)
    (args.out_dir/'reader-prompt.txt').write_text(job['prompt'])
    write(args.out_dir/'source-record.json',record)
    write(args.out_dir/'source-units-context.json',enriched)
    write(args.out_dir/'article-index.json',index)
    result = dict(source_id=args.source_id, original_task_id=case['original_task_id'],
        acquired_text_sha256=digest, xml_sha256=sha(args.article_xml), original_unit_fields_unchanged=True,
        source_units=len(original), context_states=dict(Counter(u['original_context']['status'] for u in enriched)),
        prompt_chars=len(job['prompt']), network_requests=0, model_calls=0,
        scientific_assessment='not_performed', eligibility_and_IF='not_established_by_acquisition',
        limits='Known task, not unused control or generalization result. All acquired text is supplied; reference/heading/unmatched units remain explicitly unbound. No token-budget verification or model execution yet.')
    if args.include_structure:
        result.update(structure_states=dict(Counter(u['original_structure']['status'] for u in enriched)),
            structure_scope_sets=dict(Counter('|'.join(u['original_structure'].get('possible_scopes',[])) or 'unknown'
                                             for u in enriched)),
            limits='Known task, not unused control or generalization result. All acquired text preserved. Exact XML structure marks original locations including bibliography; ambiguities remain explicit. No token-budget verification, model reading or semantic judgment yet.')
    assert all(sha(Path(p)) == digest for p,digest in frozen.items())
    write(args.out_dir/'result.json',result)
    manifest = {str(p.relative_to(args.out_dir)):sha(p) for p in args.out_dir.rglob('*') if p.is_file()}
    write(args.out_dir/'MANIFEST.json',manifest)
    assert all(sha(args.out_dir/p)==digest for p,digest in manifest.items())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
