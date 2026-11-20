"""Offline annotation metrics; missing labels and unpaired settings stay explicit.

Claim rates are descriptive pooled counts. Their Wilson intervals assume
independent claims and do not model within-report dependence. Paired effects
use a deterministic bootstrap over matched reports, separately per domain.
"""
from __future__ import annotations
import argparse
import json
import math
import random
from pathlib import Path

LABELS = {'supported', 'partial', 'unsupported', 'contradicted', 'unverifiable'}
MATCH_KEYS = ('model', 'temperature', 'source_pack_sha256', 'settings_sha256')


def _rate(numerator, denominator):
    if not denominator:
        return {'numerator': numerator, 'denominator': denominator, 'rate': None, 'wilson95_descriptive': None}
    p, z = numerator / denominator, 1.96
    d = 1 + z*z/denominator
    center = (p + z*z/(2*denominator))/d
    half = z*math.sqrt(p*(1-p)/denominator + z*z/(4*denominator**2))/d
    return {'numerator': numerator, 'denominator': denominator, 'rate': p,
            'wilson95_descriptive': [max(0, center-half), min(1, center+half)]}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evaluate(run):
    cases = run.get('cases', [])
    claims = [claim for case in cases for claim in case.get('claims', [])]
    labelled = [c for c in claims if c.get('grounding') in LABELS]
    unknown_labels = [c['grounding'] for c in claims if c.get('grounding') is not None and c['grounding'] not in LABELS]
    if unknown_labels:
        raise ValueError('Invalid grounding labels')
    entailment = [c['citation_entails'] for c in claims if isinstance(c.get('citation_entails'), bool)]
    coverage = [c['evidence_covered'] for c in claims if isinstance(c.get('evidence_covered'), bool)]
    result = {'run': run.get('system', 'unknown'), 'case_count': len(cases), 'claim_count': len(claims),
              'grounding_annotated_count': len(labelled), 'grounding_missing_count': len(claims)-len(labelled)}
    for label in sorted(LABELS):
        result[label+'_claim_rate'] = _rate(sum(c['grounding']==label for c in labelled), len(labelled))
    result['citation_entailment_rate'] = _rate(sum(entailment), len(entailment))
    result['evidence_coverage_rate'] = _rate(sum(coverage), len(coverage))
    for key in ('usefulness', 'latency_seconds', 'model_calls', 'tool_calls'):
        values = [c[key] for c in cases if _number(c.get(key))]
        result[key] = {'n': len(values), 'missing': len(cases)-len(values), 'mean': sum(values)/len(values) if values else None}
    engines = {}
    for case in cases:
        for engine, row in (case.get('retrieval') or {}).items():
            slot = engines.setdefault(engine, {'tp':0, 'retrieved':0, 'gold_relevant':0, 'recall_tp':0, 'precision_cases':0, 'recall_cases':0, 'missing_gold_cases':0})
            tp, retrieved, gold = row.get('relevant_retrieved'), row.get('retrieved'), row.get('gold_relevant')
            if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (tp, retrieved)) or tp > retrieved:
                raise ValueError('Retrieval requires nonnegative relevant_retrieved <= retrieved')
            slot['tp'] += tp; slot['retrieved'] += retrieved; slot['precision_cases'] += 1
            if gold is None:
                slot['missing_gold_cases'] += 1
            elif not isinstance(gold, int) or isinstance(gold, bool) or gold < tp:
                raise ValueError('gold_relevant must be nonnegative and >= relevant_retrieved')
            else:
                slot['recall_tp'] += tp; slot['gold_relevant'] += gold; slot['recall_cases'] += 1
    result['retrieval_by_engine'] = {engine: {**slot,
        'precision':_rate(slot['tp'],slot['retrieved']),
        'recall':_rate(slot['recall_tp'],slot['gold_relevant'])} for engine,slot in engines.items()}
    return result


def _bootstrap(deltas, families=None):
    if not deltas:
        return {'n':0, 'mean_delta':None, 'bootstrap95':None}
    clusters={}
    for family, delta in zip(families or list(range(len(deltas))), deltas):
        clusters.setdefault(family, []).append(delta)
    groups=list(clusters.values())
    rng=random.Random(20261110)
    samples=[]
    for _ in range(2000):
        drawn=[value for group in rng.choices(groups,k=len(groups)) for value in group]
        samples.append(sum(drawn)/len(drawn))
    samples.sort()
    return {'n':len(deltas),'task_families':len(groups),'mean_delta':sum(deltas)/len(deltas),
            'bootstrap95': [samples[49],samples[1949]] if len(groups)>1 else None}


def paired(baseline, candidate):
    def keyed(run):
        out={}
        for case in run.get('cases',[]):
            key=case.get('case_id')
            if not key or key in out: raise ValueError('Missing or duplicate case_id')
            out[key]=case
        return out
    b,c=keyed(baseline),keyed(candidate)
    mismatches=[]; matched=[]
    for key in sorted(b.keys() & c.keys()):
        bad=[field for field in MATCH_KEYS if b[key].get(field) is None or b[key].get(field)!=c[key].get(field)]
        if not b[key].get('domain') or b[key].get('domain')!=c[key].get('domain'): bad.append('domain')
        if bad: mismatches.append({'case_id':key,'fields':bad})
        else: matched.append(key)
    groups={}
    for group in ['all']+sorted({b[k]['domain'] for k in matched}):
        ids=[k for k in matched if group=='all' or b[k]['domain']==group]
        deltas={}
        for metric in ('unsupported_claim_rate','contradicted_claim_rate','citation_entailment_rate','evidence_coverage_rate','usefulness','latency_seconds'):
            values=[]; families=[]
            for key in ids:
                x,y=evaluate({'cases':[b[key]]})[metric],evaluate({'cases':[c[key]]})[metric]
                vx,vy=x.get('rate',x.get('mean')),y.get('rate',y.get('mean'))
                if vx is not None and vy is not None:
                    values.append(vy-vx);families.append(b[key].get('task_family',key))
            deltas[metric]=_bootstrap(values,families)
        groups[group]=deltas
    return {'status':'computed' if matched and not mismatches and b.keys()==c.keys() else 'incomplete_pairing',
            'baseline':evaluate(baseline),'candidate':evaluate(candidate),'matched_cases':len(matched),
            'unmatched_baseline':sorted(b.keys()-c.keys()),'unmatched_candidate':sorted(c.keys()-b.keys()),
            'configuration_mismatches':mismatches,'paired_report_deltas_by_domain':groups,
            'assessment_provenance':{'baseline':baseline.get('assessment',{'independence':'unreported'}),'candidate':candidate.get('assessment',{'independence':'unreported'})},
            'limitations':['Gold recall is known-pool recall, not all-literature recall.',
                'Wilson intervals are descriptive; paired bootstrap samples task families when supplied, otherwise reports.',
                'Small samples, annotation dependence and missing labels limit inference; no effectiveness pass is assigned.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();encoded=json.dumps(paired(json.loads(a.baseline.read_text()),json.loads(a.candidate.read_text())),ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.write_text(encoded,encoding='utf-8')
    else:print(encoded,end='')


if __name__=='__main__':main()
