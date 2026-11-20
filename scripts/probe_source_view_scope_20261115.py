"""Compare real source creation/rendering against preserved pre-fix code."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import typing

from research_verify import generation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-manifest',type=Path,action='append',required=True)
    p.add_argument('--baseline-generation',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    cases=[json.loads(path.read_text())['cases'][0] for path in a.case_manifest]
    files=[Path(__file__),a.baseline_generation,*a.case_manifest,*[Path(c['source']) for c in cases],
        Path('local_deep_research/overlay/base_citation_handler.py'),
        *Path('local_deep_research/research_verify').glob('*.py')]
    frozen={str(f):sha(f) for f in files};write(a.out_dir/'prestart-freeze.json',frozen)
    for f in files:
        if str(f).startswith(('scripts/','local_deep_research/')):
            target=a.out_dir/'code'/f;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
    old=dict(vars(generation));tree=ast.parse(a.baseline_generation.read_text())
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'source_material','_source_blocks'}]
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(a.baseline_generation),'exec'),old)
    overlay=Path('local_deep_research/overlay/base_citation_handler.py')
    tree=ast.parse(overlay.read_text())
    method=next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body
        if isinstance(n,ast.FunctionDef) and n.name=='_create_documents')
    results=[]
    for index,case in enumerate(cases):
        assert sha(Path(case['source']))==case['source_sha256']
        records=json.loads(Path(case['source']).read_text())
        groups=[]
        for name,reader in [('old',old['source_material']),('new',generation.source_material)]:
            scope=dict(Union=typing.Union,List=typing.List,Dict=typing.Dict,Document=SimpleNamespace,source_material=reader)
            exec(compile(ast.Module(body=[method],type_ignores=[]),str(overlay),'exec'),scope)
            groups.append(scope['_create_documents'](None,copy.deepcopy(records)))
        assert [d.page_content for d in groups[0]]==[d.page_content for d in groups[1]]
        for complete in [False,True]:
            old_views=[];new_views=[]
            before=list(old['_source_blocks'](groups[0],case['query'],old_views,complete_acquired=complete))
            after=list(generation._source_blocks(groups[1],case['query'],new_views,complete_acquired=complete))
            assert [(v['index'],v['text']) for v in old_views]==[(v['index'],v['text']) for v in new_views]
            prefix=f'case-{index}-'+('complete' if complete else 'selected')
            (a.out_dir/(prefix+'-old.txt')).write_text('\n\n'.join(block for _,block in before))
            (a.out_dir/(prefix+'-new.txt')).write_text('\n\n'.join(block for _,block in after))
            changes=[]
            for left,right in zip(old_views,new_views):
                line=lambda block:next(line for line in block.splitlines() if line.startswith('Evidence type:'))
                if line(left['block'])!=line(right['block']):
                    changes.append(dict(source_id=right['index'],before=line(left['block']),after=line(right['block']),
                        model_view_kind=right['view_kind'],text_sha256=right['model_view_sha256']))
            results.append(dict(case_manifest=str(a.case_manifest[index]),complete_acquired=complete,
                sources=len(records),all_acquired_text_unchanged=True,all_model_view_text_unchanged=True,
                scope_changes=changes,semantic_assessment='not_performed'))
    assert all(sha(Path(f))==digest for f,digest in frozen.items())
    write(a.out_dir/'results.json',results)
    manifest={str(f.relative_to(a.out_dir)):sha(f) for f in a.out_dir.rglob('*') if f.is_file()}
    write(a.out_dir/'MANIFEST.json',manifest)
    assert all(sha(a.out_dir/f)==digest for f,digest in manifest.items())
    print(json.dumps([dict(case=r['case_manifest'],complete=r['complete_acquired'],sources=r['sources'],
        changed_labels=len(r['scope_changes'])) for r in results]))


if __name__=='__main__':
    main()
