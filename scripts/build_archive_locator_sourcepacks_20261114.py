"""Recover original locator URIs from actual archived PDF annotations, offline."""
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from pypdf import PdfReader
from research_verify.original_reference import matching_pdf_annotations, original_reference_urls


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--assembly-audit',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    assembly=json.loads(a.assembly_audit.read_text());a.out_dir.mkdir(parents=True,exist_ok=False)
    inputs={str(a.assembly_audit):sha(a.assembly_audit)};reports=[]
    for n,row in enumerate(assembly['reports']):
        source_path=Path(row['source_pack_path']);assert sha(source_path)==row['source_pack_sha256']
        text_path=Path(row['report_path']);assert sha(text_path)==row['original_report_sha256']
        pdf_path=text_path.with_suffix('.pdf');pdf_sha=sha(pdf_path)
        assert subprocess.check_output(['pdftotext','-layout',str(pdf_path),'-'])==text_path.read_bytes()
        inputs.update({str(source_path):sha(source_path),str(text_path):sha(text_path),str(pdf_path):pdf_sha})
        annotations=[]
        for page_number,page in enumerate(PdfReader(pdf_path).pages,1):
            for index,reference in enumerate(page.get('/Annots',[])):
                annotation=reference.get_object();uri=(annotation.get('/A')or{}).get('/URI')
                if uri:
                    annotations.append(dict(url=str(uri),page=page_number,annotation_index=index,
                        object_id=getattr(reference,'idnum',None),rect=[float(x)for x in annotation.get('/Rect',[])]))
        original=json.loads(source_path.read_text());sources=copy.deepcopy(original);bindings=[]
        for source in sources:
            evidence=matching_pdf_annotations(source,annotations,pdf_sha)
            if evidence:source['original_locator_annotations']=evidence
            try:
                anchors=original_reference_urls(source)
                status='one_locator'if len(anchors)==1 else'ambiguous_or_missing_locator'
            except ValueError as exc:
                anchors=[];status=str(exc)
            bindings.append(dict(source_index=source['index'],status=status,locators=anchors))
        assert all(before=={k:v for k,v in after.items()if k!='original_locator_annotations'}for before,after in zip(original,sources,strict=True))
        folder=a.out_dir/f'report-{n:02d}';folder.mkdir()
        pack=folder/'sources.json';pack.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
        (folder/'pdf-uri-annotations.json').write_text(json.dumps(dict(pdf_path=str(pdf_path),pdf_sha256=pdf_sha,annotations=annotations),ensure_ascii=False,indent=2)+'\n')
        reports.append(dict(report_path=str(text_path),pdf_path=str(pdf_path),pdf_sha256=pdf_sha,
            original_source_pack_sha256=sha(source_path),source_pack_path=str(pack),source_pack_sha256=sha(pack),
            original_identity_metadata_preserved=True,pdf_to_archived_text_exact=True,
            sources=len(sources),uri_annotations=len(annotations),bindings=bindings))
    for path in [Path(__file__),Path('local_deep_research/research_verify/original_reference.py')]:
        inputs[str(path)]=sha(path);target=a.out_dir/'code'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    audit=dict(scope='Actual archived-PDF URI locator recovery only; no paper identity, eligibility, outcome or correction acceptance',
        inputs=inputs,reports=reports,newly_credited_corrections=0,quality_claim=None)
    (a.out_dir/'assembly-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(sources=r['sources'],uri_annotations=r['uri_annotations'],single_locator=sum(b['status']=='one_locator'for b in r['bindings']))for r in reports]))


if __name__=='__main__':main()
