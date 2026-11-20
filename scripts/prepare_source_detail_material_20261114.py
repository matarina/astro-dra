"""No-model preflight using the actual document-creation method and detail cache."""
import argparse,ast,hashlib,json,typing
from pathlib import Path
from types import SimpleNamespace
from research_verify.generation import source_material
from research_verify.source_detail_material import format_source_details


def native_documents(sources):
    path=Path('local_deep_research/overlay/base_citation_handler.py')
    tree=ast.parse(path.read_text())
    method=next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body
                if isinstance(n,ast.FunctionDef) and n.name=='_create_documents')
    scope={'Union':typing.Union,'List':typing.List,'Dict':typing.Dict,'Document':SimpleNamespace,
           'source_material':source_material}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    return scope['_create_documents'](None,sources)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache-dir',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    root=Path('evaluation/frontier-strategy-20261113')
    sources=json.loads((root/'immune-evidence/production-original-sourcepack.json').read_text())['sources']
    cache=[json.loads(p.read_text()) for p in a.cache_dir.glob('source-*.json')]
    query=(root/'full-source-reader-input-query-20261114.txt').read_text()
    required=json.loads((root/'immune-evidence/production-agent-draft-0002.metadata.json').read_text())['cited_internal_ids']
    material,r=format_source_details(native_documents(sources),query,cache,max_chars=60000,required_ids=required)
    (a.out_dir/'material.txt').write_text(str(material));(a.out_dir/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    # Post-planning evaluator-only scope. Never enters cache loading or allocation.
    packet=json.loads((root/'immune-evidence/packet.json').read_text());rows=[]
    for issue in packet['rows']:
        for n,span in enumerate(issue.get('acquired_method_spans') or []):
            rows.append(dict(source_id=issue['production_source_id'],span=n,exact=span['text'] in material,
                             prefix80=span['text'][:80] in material))
    (a.out_dir/'evaluator-only-exposure.json').write_text(json.dumps(dict(scope='Literal preflight exposure only; not support/correction',rows=rows),indent=2)+'\n')
    print(json.dumps(dict(chars=len(material),sources=len(material.views),exact=sum(r['exact'] for r in rows),prefix80=sum(r['prefix80'] for r in rows))))


if __name__=='__main__':main()
