"""Offline-enrich a completed source snapshot with jcr_mcp metrics."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--sources',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--minimum-if',type=float,default=10.0); args=p.parse_args()
    from research_verify.jcr_adapter import lookup_source
    sources=json.loads(args.sources.read_text()); found=0
    for source in sources:
        result=lookup_source(source,minimum=args.minimum_if,operator='>=',year='latest')
        source['_jcr_check']=result
        source['jcr_check_status']=result.get('status')
        source['jcr_provenance']={'source':'jcr_mcp','metric_year':result.get('metric_year'),'metric_source':result.get('metric_source'),'source_url':result.get('source_url'),'status':result.get('status'),'missing_reason':result.get('missing_reason'),'requested_minimum_if':result.get('minimum_if'),'threshold_operator':result.get('threshold_operator')}
        if result.get('status')=='found':
            found+=1; source['impact_factor']=result.get('impact_factor'); source['metric_year']=result.get('metric_year'); source['passes_threshold']=result.get('passes_threshold')
    args.output.write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sources':len(sources),'found':found,'output':str(args.output)},ensure_ascii=False))
if __name__=='__main__': main()
