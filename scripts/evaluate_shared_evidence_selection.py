"""Small frozen selector evaluation; no model or report-quality claim."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import sys
ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'local_deep_research'))
from research_verify.evidence_selection import select_context_windows
from research_verify.retrieval import fallback_query_candidates

CASES=[
 {"name":"biomedical_spatial","pool":ROOT/'evaluation/fixed-source-role-20261112/case6-sources.json',"query":"spatial transcriptomics adipose tissue methods platform","needles":["spatial","adipose"]},
 {"name":"nonbiomedical_qasper","pool":Path('/data1/maxw/ldr-evaluation/bioasq-native-20261111/qasper_1803_02155-sources.json'),"query":"relative positions distances in self attention","needles":["relative","position"]},
 {"name":"cross_language_no_overlap","pool":Path('/data1/maxw/ldr-evaluation/bioasq-native-20261111/qasper_1803_02155-sources.json'),"query":"中文问题：模型如何表示距离？","needles":["relative","position","distance"]},
]
rows=[]
for case in CASES:
 pool=json.loads(case['pool'].read_text())
 text='\n\n'.join(str(s.get('abstract') or s.get('body') or s.get('content') or '') for s in pool)
 windows=select_context_windows(text,case['query'],window_chars=1600,max_windows=3,context_chars=4800)
 joined='\n'.join(w.text.casefold() for w in windows)
 rows.append({"case":case['name'],"source_sha256":hashlib.sha256(case['pool'].read_bytes()).hexdigest(),"source_count":len(pool),"windows":len(windows),"methods":sorted(set(w.method for w in windows)),"needles_visible":{n:n.casefold() in joined for n in case['needles']},"selected_offsets":[[w.start,w.end] for w in windows],"lexical_match_flags":[w.lexical_match for w in windows],"fallback_not_candidates": fallback_query_candidates('cancer NOT pediatric')==[]})
out={"schema_version":"shared_evidence_selection_smoke.v1","status":"evaluation_only","cases":rows,"interpretation":["Uses real frozen biomedical and QASPER source packs; no generated report is scored.","Needle visibility is a retrieval/context check, not citation entailment or hallucination measurement.","The NOT case confirms the fallback preserves Boolean semantics rather than retrieving pediatric cancer as a positive term."]}
output = Path(__import__('os').environ.get(
    'SHARED_SELECTOR_OUTPUT', 'evaluation/method-first-20261112/shared-selector-results.json'))
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
