"""Summarize native known-item locating; distinguish upstream failure from empty."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean


def collect(root):
    result={'scope':'known-item locating at native preview budget 25, not full-literature recall or relevance precision','arms':{},'effectiveness':'unproven'}
    all_rows={}
    for arm in ('baseline','candidate','searxng-isolated','searxng-alternatives-verified'):
        rows=[]
        for path in sorted((root/arm).glob('*.json')):
            row=json.loads(path.read_text());upstream=[]
            for event in row['requests']:
                if not event.get('file'):continue
                payload=(root/arm/event['file']).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=event['sha256']:raise ValueError('HTTP body changed')
                try:data=json.loads(payload)
                except (ValueError,UnicodeDecodeError):continue
                if isinstance(data,dict) and isinstance(data.get('unresponsive_engines'),list):upstream.extend(data['unresponsive_engines'])
            row['upstream_failures']=upstream
            if not row.get('returned_count') and upstream:row['effective_status']='empty_with_upstream_failures'
            elif row.get('transport_failures'):
                row['effective_status']='partial_with_transport_failures' if row.get('returned_count') else 'empty_with_transport_failures'
            else:row['effective_status']=row['status']
            rows.append(row)
        if not rows:continue
        all_rows[arm]=rows
        grouped={}
        for engine in sorted({r['engine'] for r in rows}):
            group=[r for r in rows if r['engine']==engine]
            grouped[engine]={'scheduled':len(group),'hit_count':sum(r.get('known_item_hit',False) for r in group),'hit_denominator':len(group),'returned_total':sum(r.get('returned_count',0) for r in group),'mean_latency_seconds':mean(r['latency_seconds'] for r in group),'http_requests':sum(len(r['requests']) for r in group),'transport_failures':sum(r['transport_failures'] for r in group),'empty_with_upstream_failures':sum(r['effective_status']=='empty_with_upstream_failures' for r in group),'cases':[{k:r.get(k) for k in ('case_id','known_item_hit','target_ranks','returned_count','latency_seconds','effective_status','upstream_failures')} for r in group]}
        result['arms'][arm]=grouped
    pairs=[]
    for b in all_rows.get('baseline',[]):
        c=next((x for x in all_rows.get('candidate',[]) if x['case_id']==b['case_id'] and x['engine']==b['engine']),None)
        if c is None:continue
        def ids(row):return {s.get('pmid') or s.get('id') or s.get('link') for s in row.get('sources',[])}
        bs,cs=ids(b),ids(c)
        pairs.append({'case_id':b['case_id'],'baseline_hit':b.get('known_item_hit'),'candidate_hit':c.get('known_item_hit'),'shared_identifiers':len(bs&cs),'baseline_only_identifiers':len(bs-cs),'candidate_only_identifiers':len(cs-bs)})
    result['pubmed_pairs']=pairs
    result['limitations']=['Cases were fixed before candidate, but candidate motivation used baseline traces; development probe, not unseen hold-out.','PubMed and Europe PMC no-LLM previews bypass native reranking/selection.','Different engines have different query interpretation and sort orders; counts are not comparable relevance estimates.','SearXNG HTTP200 with upstream errors is availability evidence, not literature absence.','Isolated SearXNG changes deployment route/backend configuration; it is not a paired code-only experiment.','Live requests are sequential and web index state may change; no randomized crossover or uncertainty estimate from six cases.']
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=collect(a.root);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for arm,engines in result['arms'].items():
        for engine,stats in engines.items():print(arm,engine,{k:v for k,v in stats.items() if k!='cases'})
