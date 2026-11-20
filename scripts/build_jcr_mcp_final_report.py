"""Build a transparent IF-enriched report without mutating the original report."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

PMID_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov|europepmc\.org/article/(?:MED|PMC))/([0-9]+)", re.I)


def source_key(source):
    return str(source.get("pmid") or "").strip()


def result_line(source):
    check = source.get("_jcr_check") or {}
    if check.get("status") == "found":
        return f"- **IF:** {check.get('impact_factor')} (JCR {check.get('metric_year')}; jcr_mcp ShowJCR)"
    return "- **IF:** unknown (jcr_mcp identity/metric unavailable)"


def inline_if(source):
    check = source.get("_jcr_check") or {}
    if check.get("status") == "found":
        return f"JCR IF {check.get('impact_factor')} ({check.get('metric_year')}; jcr_mcp)"
    return "JCR IF unknown (identity/metric unavailable)"

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=args.report.read_text(); sources=json.loads(args.sources.read_text())
    by_pmid={source_key(s):s for s in sources if source_key(s)}
    found=[s for s in sources if (s.get('_jcr_check') or {}).get('status')=='found']
    current=None; out=[]; in_sources=False
    for line in report.splitlines():
        if line.strip().lower() in {"## sources", "### sources"}:
            in_sources=True
        m=re.search(r'\*\*PMID:\*\*\s*([0-9]+)',line)
        if m:
            current=by_pmid.get(m.group(1))
        # DS4.1's report uses inline PubMed/Europe PMC URLs instead of PMID
        # fields. Resolve the record before writing its IF annotation.
        for pmid in PMID_RE.findall(line):
            if pmid in by_pmid:
                current=by_pmid[pmid]
                break
        if line.strip().startswith('- **IF:**') and current:
            line=result_line(current)
        elif current and in_sources and line.strip().startswith(("URL:", "DOI:")):
            # Keep the source list self-contained for readers who do not open
            # the preceding verification table.
            if line.strip().startswith("DOI:"):
                line += f"\n   {inline_if(current)}"
        out.append(line)

    # The local DS4.1 report has no per-record IF field. Add one immediately
    # after each candidate URL line, preserving the model's text verbatim
    # apart from this deterministic metadata annotation.
    annotated=[]; source_section=False
    for line in out:
        annotated.append(line)
        if not source_section and line.lstrip().startswith(("URL:", "- URL:")):
            pmids=PMID_RE.findall(line)
            source=next((by_pmid[p] for p in pmids if p in by_pmid), None)
            if source:
                annotated.append(f"   {inline_if(source)}")
        if line.strip().lower() in {"## sources", "### sources"}:
            source_section=True
    out=annotated

    # Remove statements that only described the pre-correction report. The
    # original report remains untouched; this overlay states what is now
    # supported by the attached JCR records.
    text='\n'.join(out)
    text=text.replace(
        '所有摘要均未提供影响因子数值，因此无法验证“IF>10”，也无法按IF排序 [1–20]。',
        '原始摘要未提供影响因子数值；前置的 source-bound JCR 表和逐条标注为可匹配记录补充了 IF。身份或指标未匹配的记录仍不能验证“IF>10”。',
    )
    text=text.replace(
        '但IF未提供，不能按IF排序，且不足以构成20篇：',
        '但仍有身份未匹配，不能将全部候选按IF排序，且不足以构成20篇：',
    )
    text=text.replace(
        '并明确标注IF和每组样本数缺失。',
        '并明确标注可匹配的IF、未匹配身份和每组样本数缺失。',
    )
    table=['## JCR IF verification (source-bound)','', 'These values are attached to the collected source records by jcr_mcp and override missing IF metadata in the original abstract records.','', '| Source index | Journal | IF | Metric year | IF≥10 |','|---:|---|---:|---:|---|']
    for s in found:
        c=s['_jcr_check']; table.append(f"| {s.get('index')} | {s.get('journal','')} | {c.get('impact_factor')} | {c.get('metric_year')} | {'yes' if c.get('passes_threshold') else 'no'} |")
    table += ['', f'jcr_mcp found numeric IF for {len(found)} of {len(sources)} collected sources. Unmatched identities remain unknown.']
    args.output.write_text('\n'.join(table)+'\n\n'+text+'\n')
    print(json.dumps({'output':str(args.output),'found':len(found),'sources':len(sources)},ensure_ascii=False))
if __name__=='__main__': main()
