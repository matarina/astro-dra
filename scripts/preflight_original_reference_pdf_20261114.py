"""Bounded original-reference locator acquisition; no model or source-pack mutation."""
import argparse,hashlib,io,json
from pathlib import Path
from research_verify.original_reference import original_reference_urls
from research_verify.evidence_fetch import EvidenceFetcher
from scripts.experiment_error_receipt import error_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--source-id',type=int,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    source=next(s for s in json.loads(a.sources.read_text())if int(s['index'])==a.source_id);anchors=original_reference_urls(source)
    if len(anchors)!=1:raise ValueError('Original reference URL ambiguous or unavailable')
    anchor=anchors[0];(a.out_dir/'original-source.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})
    fetch=EvidenceFetcher(snap,requests=1,seconds=30)
    result=dict(scope='Original archived URL locator acquisition under native policy; no stable paper identity or semantic acceptance',source_pack_sha256=hashlib.sha256(a.sources.read_bytes()).hexdigest(),anchor=anchor,maximum_requests=1,maximum_bytes=8_000_000,model_calls=0)
    try:
        raw=fetch.read_bytes(anchor['url'],limit=8_000_000);path=a.out_dir/'document.bin';path.write_bytes(raw)
        result.update(raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw))
        if not raw.lstrip().startswith(b'%PDF'):raise ValueError('Response is not a PDF document')
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(raw));result['pages']=len(reader.pages)
        if len(reader.pages)>40:raise ValueError('PDF exceeds page extraction bound')
        pages=[page.extract_text()or''for page in reader.pages]
        for n,text in enumerate(pages):(a.out_dir/f'page-{n+1:03d}.txt').write_text(text)
        text='\n\n'.join(pages);(a.out_dir/'document-text.txt').write_text(text)
        result.update(status='retrieved_and_extracted',text_sha256=hashlib.sha256(text.encode()).hexdigest(),text_chars=len(text),
            page_hashes=[hashlib.sha256(t.encode()).hexdigest()for t in pages])
    except Exception as exc:result.update(status='unavailable',**error_receipt(exc))
    result.update(transport_events=fetch.events,limits=['Locator equality does not bind DOI/PMID or establish relevance','No text added to report or frozen source pack','PDF extraction can be lossy; inspect pages/metadata independently','Requested URL recorded; redirect destination not separately captured'],quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
