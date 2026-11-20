"""Read-only keyword search over captured pipeline boundaries; no semantic verdict."""
from pathlib import Path
import argparse,collections,datetime,json

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('text');p.add_argument('--case',default='');p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--max-files',type=int,default=200);a=p.parse_args();needle=a.text.casefold();rows=[]
 for case in sorted(a.root.glob('[0-9][0-9]-*')):
  if not case.is_dir()or a.case not in case.name:continue
  files=[]
  for kind in ['provider-io','search-io','collection-io','full-trace']:
   files += [x for x in (case/kind).glob('*/*.json')if x.name not in ['receipt.json','finish.json']]
  files += [x for x in (case/'results').glob('*')if x.is_file()and x.suffix in ['.json','.md']]
  for f in sorted(files):
   raw=f.read_text(errors='replace');pos=raw.casefold().find(needle)
   if pos<0:continue
   receipt=f.parent/'receipt.json';at=f.stat().st_mtime;stage=f.parent.parent.name
   try:
    content=json.loads(raw)
    if isinstance(content,dict):at=content.get('at',content.get('started_unix',at))
   except json.JSONDecodeError:pass
   if receipt.exists():
    r=json.loads(receipt.read_text());at=r.get('at',r.get('ended_unix'if f.name.startswith('response')else'started_unix',at));stage=r.get('stage',stage)
    for frame in r.get('call_stack',[]):
     if frame.get('stage'):stage=frame['stage'];break
   rows.append({'case':case.name,'at':at,'stage':stage,'file':str(f.relative_to(a.root)),'inspect_page':str((f.parent/'inspect.html').relative_to(a.root))if(f.parent/'inspect.html').exists()else None,'context':raw[max(0,pos-120):pos+len(a.text)+220]})
 rows.sort(key=lambda r:(r['case'],r['at'],r['file']));counts=collections.Counter((r['case'],r['stage'])for r in rows)
 print(json.dumps({'query':a.text,'matched_files':len(rows),'counts_by_case_and_boundary':[{'case':c,'stage':s,'files':n}for(c,s),n in sorted(counts.items())],'displayed_files':min(len(rows),max(0,a.max_files)),'scope':'Text occurrence only; not proof of model understanding, semantic support or correction.'},ensure_ascii=False,indent=2))
 for row in rows[:max(0,a.max_files)]:print(json.dumps(row,ensure_ascii=False))
if __name__=='__main__':main()
