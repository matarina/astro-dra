"""Compare preserved archive reports by evidence/issue class.

This is an audit artifact, not a hallucination-rate estimator. It records runtime
policy, source/report structural facts and a manual issue-status table; it does
not infer scientific support from keywords or citation counts.
"""
from __future__ import annotations
import gzip, json, re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).parents[1]
CURRENT=Path(__file__).parents[1]/'evaluation/archive-prompt-reviewed-20261112/results'
PRIOR=Path('/data1/maxw/ldr-evaluation/archive-prompt-run-20261111/results')
PAIRS=[
 ('archive-6927b167c196','KRAS G12C机制'),
 ('archive-47c54edcc0eb','四类免疫细胞单细胞方案'),
 ('archive-41d13d68b84e','RNA额外峰/污染'),
 ('archive-6ac5d65ed736','2026肿瘤 IF>10/20篇/空间'),
 ('archive-90ad0dce1609','中文糖尿病神经病变'),
 ('archive-a9b2517baf83','脂肪空间转录组'),
 ('archive-6e8e8d113e76','Xenium'),
]
MANUAL={
 'archive-6927b167c196': {'status':'appears_addressed_at_report_level','issue':'机制链缺失','basis':'当前稿明确GTPase/GAP水解受损、GTP结合状态、RAF/MEK/ERK与后果；来源池与前稿不同，未独立医学复核。'},
 'archive-47c54edcc0eb': {'status':'partially_addressed','issue':'平台/技术混用、marker和四类统一方案','basis':'当前稿分开平台/方法并明确没有统一四类面板；native review仍保留两条“来源未报告的总体样本来源/推荐方案”缺口。'},
 'archive-41d13d68b84e': {'status':'appears_addressed_at_report_level','issue':'把额外峰直接当细菌污染/硬阈值','basis':'当前稿明确没有直接证据、拒绝仅凭低峰放弃测序，并区分RIN/峰形/下游污染核查；建议仍是推断，未独立实验确认。'},
 'archive-6ac5d65ed736': {'status':'addressed_as_evidence_boundary','issue':'IF数值/IF排序/凑20篇与平台、样本数缺证','basis':'当前稿拒绝声称IF>10或20篇，保留unknown和平台/分组缺口；因此用户的数量目标未满足，但证据边界未被伪造。'},
 'archive-90ad0dce1609': {'status':'scope_disclosed_but_request_unfulfilled','issue':'中文-only请求混入英文','basis':'当前稿开头明确绝大多数来源英文、未确认符合中文发表条件；它仍不能提供中文-only综述，未把英文来源伪装成中文。'},
 'archive-a9b2517baf83': {'status':'partially_addressed','issue':'SLACS/空间范围/IF排序','basis':'当前稿未出现SLACS，IF为unknown，并把非空间研究标为排除；来源池仍需人工核查平台与脂肪样本范围。'},
 'archive-6e8e8d113e76': {'status':'structurally_addressed_pending_semantics','issue':'重复、身份和厂商/博客混入','basis':'当前source snapshot的ID和URL无重复；当前稿保留平台局限并混合论文/预印本，仍需独立语义与身份审阅。'},
}
def metrics(path):
 if not (path/'summary.json').exists():
  return {'available':False,'path':str(path)}
 d=json.loads((path/'summary.json').read_text()); report=(path/'report.md').read_text(errors='replace')
 sources=json.loads((path/'sources.json').read_text()) if (path/'sources.json').exists() else []
 ids=[str(x.get('index')) for x in sources]; urls=[str(x.get('link') or x.get('url') or '') for x in sources]
 pending=[]; calls=invalid=skipped=0
 for ep in (path/'traces').glob('*/synthesis-*/events.jsonl'):
  for line in ep.read_text(errors='replace').splitlines():
   e=json.loads(line); stage=e.get('stage')
   calls += stage=='native_check_request'; invalid += stage=='native_check_invalid'; skipped += stage=='native_check_skipped'
 for q in (path/'traces').glob('*/synthesis-*/00*-review_issue_state.json.gz'):
  e=json.loads(gzip.open(q,'rt').read()); pending.extend(e.get('pending') or [])
 return {'available':True,**d,'report_path':str(path/'report.md'),'source_path':str(path/'sources.json'),
  'citation_occurrences':len(re.findall(r'\[\[\d+\]\]',report)),
  'source_id_duplicates':len(ids)-len(set(ids)),'source_url_duplicates':len(urls)-len(set(urls)),
  'native_review_calls':calls,'native_review_invalid':invalid,'native_review_skipped':skipped,
  'native_pending':Counter(x.get('status') for x in pending),
  'if_unknown_mentions':report.lower().count('impact factor'),
  'numeric_if_mentions':len(re.findall(r'\bIF\s*[=:>]?\s*\d',report,re.I)),
  'report_language_boundary': any(s in report for s in ('绝大多数文献为英文','未确认有符合','中文发表')),
  'slacs_present':'SLACS' in report,
 }
rows=[]
for old,label in PAIRS:
 cur=CURRENT/f'reviewed-20261112-{old}'; prev=PRIOR/old
 rows.append({'case':old,'label':label,'current':metrics(cur),'prior':metrics(prev),'manual_issue_assessment':MANUAL[old]})
out={'schema_version':'archive_prompt_evidence_comparison.v1','status':'evaluation_only','prompt_source':'LDR第二次调研.rar','policy':{'model':'deepseek-v4-flash','source_engine':'live archive settings; retrieval not frozen','native_fact_consistency':True,'save_time_citation_qc':False,'production_changed':False},'rows':rows,'interpretation':["The reviewed current arm explicitly enabled native fact consistency; the earlier no-review replay is excluded from quality comparison.","Sources were live and not frozen between prior/current runs, so per-case source/report differences are descriptive, not causal model estimates.","Manual issue statuses are report-level evidence-boundary assessments, not independent biomedical gold labels.","Native review pending items remain in the denominator; no automatic deletion or hard publication gate was applied.","This artifact cannot estimate overall hallucination reduction."]}
outp=ROOT/'evaluation/archive-prompt-reviewed-comparison-20261112.json'; outp.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=list)+'\n'); print(outp)
