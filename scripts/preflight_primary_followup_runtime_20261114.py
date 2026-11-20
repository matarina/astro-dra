"""One primary article through real policy and standard overlay wiring; no LLM."""
import argparse,hashlib,json
from pathlib import Path
from research_verify.evidence_fetch import EvidenceFetcher
from scripts.run_hallucination_next_phase_experiment_20261113 import _manifest_cases
from scripts.experiment_error_receipt import error_receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args();a.out_dir.mkdir(exist_ok=False)
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    from local_deep_research.security.egress.policy import context_from_snapshot,resolve_run_primary_engine,evaluate_engine
    defaults=json.loads(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json').read_text())
    snap=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})
    case=_manifest_cases(Path('evaluation/frontier-strategy-20261113/native-original-xenium-inputs-20261114-v1/case-manifest.json'))[0]
    source=next(s for s in json.loads(case['source'].read_text())if int(s['index'])==14)
    primary=resolve_run_primary_engine(snap);ctx=context_from_snapshot(snap,primary);decision=evaluate_engine('europepmc',ctx,settings_snapshot=snap)
    events=[]
    class Capture(EvidenceFetcher):
        def read(self,url,**kw):
            n=len(events);event=dict(index=n,url=url,params=kw.get('params'));events.append(event)
            try:
                text=super().read(url,**kw);path=a.out_dir/f'response-{n:02d}.txt';path.write_text(text)
                event.update(status='retrieved',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),chars=len(text));return text
            except Exception as exc:event.update(status='unavailable',**error_receipt(exc));raise
    result=dict(scope='Isolated standard overlay runtime primary article preflight; no model or report rewriting',source=source,
                engine_decision=dict(allowed=decision.allowed,reason=decision.reason),maximum_network_requests=2,maximum_network_seconds=30)
    fetch=Capture(snap,requests=2,seconds=30)
    try:
        text=fetch.article(source)
        if text:
            path=a.out_dir/'article.txt';path.write_text(text);result.update(status='acquired',chars=len(text),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                literal_method_exposure={x:x in text for x in ['302 genes','11 groups','22 groups']})
        else:result['status']='unavailable'
    except Exception as exc:result.update(status='unavailable',**error_receipt(exc))
    result.update(transport=events,fetcher_events=fetch.events,quality_claim=None,newly_credited_corrections=0)
    (a.out_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in {'source','fetcher_events'}}))


if __name__=='__main__':main()
