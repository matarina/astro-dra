#!/usr/bin/env python3
"""Build a readable, blinded README for the preserved 48-claim review sample.

This is a presentation artifact only.  It does not assign review labels, alter
the packet, or change any production configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "evaluation/archive-claim-review-sample-20261112.json"
PACKET_PATH = ROOT / "evaluation/archive-claim-review-packet-20261112.json"
OUT_DIR = ROOT / "evaluation/archive-claim-review-20261112"
EVIDENCE_DIR = OUT_DIR / "evidence"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fence(text: str, language: str = "text") -> str:
    """Return a fenced block that cannot be closed by content backticks."""
    text = "" if text is None else str(text)
    longest = max((len(x) for x in re.findall(r"`+", text)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{text}\n{marker}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "")


def public_links(source: dict[str, Any]) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    link = clean_text(source.get("link")).strip()
    if link and link.lower() not in {"none", "null"}:
        links.append(("URL supplied by source record", link))
    doi = clean_text(source.get("doi")).strip()
    if doi and doi.lower() not in {"none", "null"}:
        links.append(("DOI", f"https://doi.org/{doi}"))
    pmid = clean_text(source.get("pmid")).strip()
    if pmid and pmid.lower() not in {"none", "null"}:
        links.append(("PMID", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"))
    return links


def source_texts(source: dict[str, Any]) -> list[tuple[str, str]]:
    """Return all supplied evidence text fields without inventing passages."""
    out: list[tuple[str, str]] = []
    for key in ("abstract", "content", "full_content", "fetched_content"):
        value = clean_text(source.get(key))
        if value and value.lower() not in {"none", "null"}:
            out.append((key, value))
    return out


def scope_by_index(reading_scope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for batch in reading_scope.get("reading_scope", []) or []:
        for item in batch.get("sources", []) or []:
            idx = clean_text(item.get("index"))
            if idx:
                result[idx] = item
    return result


def notes_by_source(reading_scope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in reading_scope.get("reading_notes", []) or []:
        for obs in note.get("observations", []) or []:
            source_id = clean_text(obs.get("source_id"))
            if source_id:
                result[source_id].append(obs)
    return result


def report_window(report: str, claim_text: str, occurrence: int) -> str:
    """Get a mechanical report window around the matching occurrence."""
    if not claim_text:
        return ""
    positions: list[int] = []
    start = 0
    while True:
        pos = report.find(claim_text, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + max(1, len(claim_text))
    if not positions:
        return ""
    pos = positions[min(occurrence, len(positions) - 1)]
    left = max(0, pos - 700)
    right = min(len(report), pos + len(claim_text) + 900)
    # Prefer complete nearby lines, while retaining the exact claim itself.
    left = report.rfind("\n", left, pos)
    left = 0 if left < 0 else left + 1
    next_line = report.find("\n", right)
    right = len(report) if next_line < 0 else next_line
    return report[left:right].strip()


def evidence_status(claim: dict[str, Any], sources: list[dict[str, Any]], scope: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    citations = [clean_text(x) for x in claim.get("citations", [])]
    source_indices = {clean_text(s.get("index")) for s in sources}
    if not citations:
        flags.append("Missing evidence: no citation index is recorded for this claim.")
    missing = [c for c in citations if c not in source_indices]
    if missing:
        flags.append("Unresolved citation: index(s) not resolved in the preserved packet: " + ", ".join(missing) + ".")
    if citations and not sources:
        flags.append("Missing evidence: the claim cites a source, but no matching source record was supplied.")
    if not sources:
        flags.append("Missing evidence: no supplied source passage is attached to this claim.")
    for source in sources:
        text_fields = {k for k, v in source_texts(source) if v.strip()}
        idx = clean_text(source.get("index"))
        scope_item = scope.get(idx, {})
        view_kind = clean_text(scope_item.get("view_kind")).lower()
        scope_text = clean_text(scope_item.get("scope")).lower()
        if view_kind == "abstract_only" or scope_text.strip() == "; complete supplied abstract":
            flags.append(f"Abstract-only access: source [{idx}] is marked abstract-only in the supplied reading scope.")
        elif "abstract_with_excerpts" in view_kind or "additional excerpts" in scope_text:
            flags.append(f"Abstract-plus-excerpts access: source [{idx}] is limited to a supplied abstract plus excerpts; full-text coverage is not established.")
        if not text_fields:
            flags.append(f"Missing evidence: source [{idx}] has no supplied abstract or full-text passage.")
    # Keep the rendered README compact while preserving distinct reasons.
    return list(dict.fromkeys(flags))


def render_source_metadata(source: dict[str, Any], scope: dict[str, Any]) -> list[str]:
    idx = clean_text(source.get("index")) or "?"
    title = clean_text(source.get("title")) or "[title missing in supplied record]"
    lines = [f"- **[{idx}] {title}**"]
    for key, label in (("doi", "DOI"), ("pmid", "PMID"), ("journal", "Journal"), ("pubdate", "Publication date")):
        value = clean_text(source.get(key)).strip()
        if value and value.lower() not in {"none", "null"}:
            if key == "doi":
                lines.append(f"  - {label}: `{value}` ([public link](https://doi.org/{value}))")
            elif key == "pmid":
                lines.append(f"  - {label}: `{value}` ([PubMed link](https://pubmed.ncbi.nlm.nih.gov/{value}/))")
            else:
                lines.append(f"  - {label}: {value}")
    supplied_link = clean_text(source.get("link")).strip()
    if supplied_link and supplied_link.lower() not in {"none", "null"}:
        lines.append(f"  - URL supplied by record: {supplied_link}")
    idx_scope = scope.get(idx)
    if idx_scope:
        scope_desc = clean_text(idx_scope.get("scope")) or "scope text not supplied"
        view_kind = clean_text(idx_scope.get("view_kind")) or "view kind not supplied"
        lines.append(f"  - Supplied reading scope: `{view_kind}` — {scope_desc}")
    else:
        lines.append("  - Supplied reading scope: no per-source scope entry was recorded.")
    return lines


def render_external_disagreements(lines: list[str]) -> None:
    """Append the preserved model-assisted disagreement audit, if available."""
    integration_path = OUT_DIR / "external-judgement-integration-20261112.json"
    if not integration_path.is_file():
        return
    payload = json.loads(integration_path.read_text(encoding="utf-8"))
    disagreements = [e for e in payload.get("claims", []) if not e.get("agreement")]
    unresolved = [e for e in disagreements if e.get("integration_status") == "disagreement_requires_human_review"]
    conservative = [e for e in disagreements if e.get("integration_status") != "disagreement_requires_human_review"]
    manual_checks = {
        ("immune_fixed_source_roles-arm-1", 78): "供应摘录只说明 sorted lung mast cells，没有明确写 FACS；Grok使用了外部Methods核验。请查[81]全文Methods，区分“sorted”与“FACS分选”，并按供应材料范围记录是否允许外部核验。",
        ("immune_fixed_source_roles-arm-1", 9): "Grok引用了[36]的完整定量/表观遗传句子，ChatGPT认为当前摘录没有这些数字。请查[36]摘要或全文，核对2 g、>10⁴、纯度/活力和DNA甲基化是否同属该研究证据。",
        ("immune_fixed_source_roles-arm-2", 11): "同一[36]表观遗传断言在另一条claim中没有附source record。请确认评阅分母按该claim的供应材料判定，还是允许引用同报告其他位置的来源记录。",
        ("immune_fixed_source_roles-arm-2", 8): "该claim没有供应source record；Grok承认只能凭已知[39]论文内容。请按预先规则决定：外部确认是否可把unverifiable改为partial，还是保持供应材料范围内unverifiable。",
        ("if_fixed_source_roles-arm-1", 68): "claim中的“仅单细胞转录组挖掘”是否排除了文章的exosomal proteomics？ChatGPT按标题/来源认定矛盾，Grok按ANXA7具体分析范围认定支持。请查[33]全文，确定‘仅’的修饰范围。",
        ("if_fixed_source_roles-arm-1", 31): "表格声称同时含单细胞和空间转录组；ChatGPT在摘录中找不到两种方法，Grok只确认研究背景。请查[13]全文Methods/图表，核实模态、期刊日期和表格‘是’是否有直接证据。",
        ("if_fixed_source_roles-arm-2", 85): "争议集中在[13]验证队列的7、500、7和1,582数字：Grok确认主研究但承认摘录没有这些数，ChatGPT因此unsupported。请查全文队列/图注，逐项核对数字和对应模态。",
        ("if_fixed_source_roles-arm-2", 157): "这是关于供应材料缺失IF/Methods的范围性建议。ChatGPT把它当作由材料缺口支持的限制陈述，Grok因无source record标为unverifiable。请先确定范围陈述是否需要逐claim citation，再按统一规则判定。",
    }
    lines.extend(
        [
            "## 外部模型辅助评阅分歧：21条（其中8条需人工复核）",
            "",
            "以下内容来自同一48条盲化sample的ChatGPT Pro和Grok模型辅助输出，单独保存于[整合记录](external-judgement-integration-20261112.md)。它不是独立生物医学评阅，也没有填入下方每条claim的空白reviewer fields。21条表示两模型verdict不同；其中8条不能用预先设定的保守合并规则化解，列为人工复核重点。",
            "",
            "### 21条分歧总表",
            "",
            "| 序号 | blind report ID | claim ID | ChatGPT Pro | Grok | 记录状态 |",
            "|---:|---|---:|---|---|---|",
        ]
    )
    for i, e in enumerate(disagreements, 1):
        lines.append(
            f"| {i} | `{e['blind_id']}` | `{e['claim_id']}` | {e['chatgpt_pro']['verdict']} | {e['grok_manual']['verdict']} | `{e['integration_status']}` |"
        )
    lines.extend(["", "### 8条关键冲突与人工核验重点", ""])
    for i, e in enumerate(unresolved, 1):
        key = (e["blind_id"], int(e["claim_id"]))
        lines.extend(
            [
                f"#### {i}. `{e['blind_id']}` / claim `{e['claim_id']}`",
                "",
                "**原始claim：**",
                "",
                fence(e["claim_text"], "text"),
                "",
                f"- 引用索引：{', '.join('[' + str(x) + ']' for x in e.get('citations', [])) if e.get('citations') else '无'}",
                f"- ChatGPT Pro：**{e['chatgpt_pro']['verdict']}**；{e['chatgpt_pro']['explanation']}",
                f"- Grok：**{e['grok_manual']['verdict']}**；{e['grok_manual']['explanation']}",
                f"- **关键冲突/人工核验：** {manual_checks.get(key, '请回到完整source snapshot和Methods核对两种判定所依赖的证据范围。')}",
                "",
            ]
        )
    lines.extend(["### 其余13条可机械保守合并的分歧", ""])
    lines.append("这些分歧均为`supported`与`partially supported`之间的12条，或`unsupported`与`unverifiable`之间的1条；整合记录分别记为`conservative:partially supported`或`conservative:unverifiable`，仍不等价于人工科学结论。")
    lines.append("")
    for i, e in enumerate(conservative, 1):
        lines.append(
            f"- {i}. `{e['blind_id']}` / claim `{e['claim_id']}`：ChatGPT **{e['chatgpt_pro']['verdict']}** vs Grok **{e['grok_manual']['verdict']}** → `{e['integration_status']}`；原文：{e['claim_text']}"
        )
    lines.extend(["", "---", ""])


def render_human_adjudication(lines: list[str]) -> None:
    """Render the user's supplied final adjudication as a separate layer."""
    path = OUT_DIR / "human-adjudication-20261112.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    claims = payload.get("claims", [])
    lines.extend(
        [
            "## 用户提供的21条最终定案（论文事实核验）",
            "",
            "以下21条是用户基于供应材料、公开摘要和可访问全文/Methods给出的最终定案，按论文事实是否成立判断。它们覆盖上面的21条模型分歧，并作为单独的人工定案记录保存；不会改写原始packet、source snapshots或下方空白reviewer fields。`confidence`是用户对该定案的信心，不等于独立专家组一致性。",
            "",
            f"最终分布：**supported {payload['counts']['supported']}**、**partially supported {payload['counts']['partially_supported']}**、**contradicted {payload['counts']['contradicted']}**。机器可读记录：[human-adjudication-20261112.json](human-adjudication-20261112.json)。",
            "",
            "| 序号 | blind report / claim | 最终 verdict | confidence | 公开证据 |",
            "|---:|---|---|---:|---|",
        ]
    )
    for i, e in enumerate(claims, 1):
        links = "<br>".join(f"[来源{j}]({link})" for j, link in enumerate(e.get("links", []), 1)) or "供应材料范围判断，无单篇论文链接"
        lines.append(f"| {i} | `{e['blind_id']} / {e['claim_id']}` | **{e['verdict']}** | {e['confidence']} | {links} |")
    lines.extend(["", "### 逐条证据与结论", ""])
    for i, e in enumerate(claims, 1):
        links = ", ".join(f"[{j}]({link})" for j, link in enumerate(e.get("links", []), 1)) or "无单篇论文链接"
        lines.extend(
            [
                f"#### {i}. `{e['blind_id']}` / claim `{e['claim_id']}` — **{e['verdict']}**（{e['confidence']}）",
                "",
                f"- 证据与结论：{e['evidence']}",
                f"- 公开链接：{links}",
                "",
            ]
        )
    lines.extend(
        [
            "### 定案中的范围和字段修正",
            "",
            "- `if_fixed_source_roles-arm-1 / 28`：空间平台应改为 **10x Genomics Visium**。",
            "- `if_fixed_source_roles-arm-1 / 31`：空间平台应改为 **10x Genomics Visium**。",
            "- `immune_fixed_source_roles-arm-2 / 11`、`immune_fixed_source_roles-arm-2 / 8`：论文事实可由全文确认，但原始sample分别存在摘录截短或claim实例无citation的来源范围限制。",
            "- `if_fixed_source_roles-arm-2 / 157`：这是供应材料完整性判断，不是论文科学结论。",
            "",
            "该部分是用户提供的人工定案，保留其公开链接和范围备注；它不构成独立专家panel或总体幻觉率估计。",
            "",
            "---",
            "",
        ]
    )


def write_evidence_file(
    path: Path,
    blind_id: str,
    claim: dict[str, Any],
    report_digest: str,
    snapshot_digest: str,
    sources: list[dict[str, Any]],
    reading_scope: dict[str, Any],
) -> None:
    scope = scope_by_index(reading_scope)
    notes = notes_by_source(reading_scope)
    lines = [
        f"# Supplied evidence for `{blind_id}` / claim `{claim['claim_id']}`",
        "",
        "This file preserves supplied evidence and reading-scope records for one blinded claim. It is an evidence packet, not a reviewer verdict.",
        "",
        f"- Blind report ID: `{blind_id}`",
        f"- Claim ID: `{claim['claim_id']}`",
        f"- Source snapshot SHA-256: `{snapshot_digest}`",
        f"- Report SHA-256: `{report_digest}`",
        "",
        "## Exact claim",
        "",
        fence(clean_text(claim.get("text")), "text"),
        "",
        "## Supplied reading scope",
        "",
    ]
    for batch in reading_scope.get("reading_scope", []) or []:
        purpose = clean_text(batch.get("purpose")) or "purpose not supplied"
        lines.append(f"- Batch `{clean_text(batch.get('batch')) or 'unspecified'}`: {purpose}")
        for item in batch.get("sources", []) or []:
            idx = clean_text(item.get("index")) or "?"
            lines.append(
                f"  - Source [{idx}]: view `{clean_text(item.get('view_kind')) or 'unknown'}`, "
                f"scope `{clean_text(item.get('scope')) or 'not supplied'}`, "
                f"available chars `{item.get('available_chars', 'unknown')}`, "
                f"model-view chars `{item.get('model_view_chars', 'unknown')}`."
            )
    if reading_scope.get("trace_available") is not None:
        lines.append(f"- Trace available flag: `{reading_scope.get('trace_available')}`")
    lines.extend(["", "## Cited source records and original supplied passages", ""])
    if not sources:
        lines.append("No source record is attached to this claim in the preserved sample.")
    for source in sources:
        idx = clean_text(source.get("index")) or "?"
        lines.extend(render_source_metadata(source, scope))
        obs = notes.get(idx, [])
        if obs:
            lines.extend(["  - Trace-selected original passages (preserved verbatim):"])
            for item in obs:
                quote = clean_text(item.get("quote"))
                if quote:
                    lines.append("    " + fence(quote, "text").replace("\n", "\n    "))
        texts = source_texts(source)
        if not texts:
            lines.append("  - No abstract, full-text, or fetched passage is supplied for this source record.")
        for field, value in texts:
            lines.extend([f"", f"  - Supplied `{field}` passage (complete recorded value):", ""])
            lines.append(fence(value, "text"))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet_arms = {
        arm["blind_id"]: (case, arm)
        for case in packet.get("cases", [])
        for arm in case.get("arms", [])
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for old in EVIDENCE_DIR.glob("claim-*.md"):
        old.unlink()

    entries: list[dict[str, Any]] = []
    occurrence_counts: dict[tuple[str, str], int] = defaultdict(int)
    for ordinal, arm in enumerate(sample.get("arms", []), start=1):
        blind_id = arm["blind_id"]
        case, packet_arm = packet_arms[blind_id]
        report = clean_text(packet_arm.get("report"))
        report_digest = hashlib.sha256(report.encode("utf-8")).hexdigest()
        snapshot_digest = clean_text(arm.get("source_snapshot_sha256"))
        scope = arm.get("reading_scope") or packet_arm.get("trace", {}).get("reading_scope", {}) or {}
        for claim_index, claim in enumerate(arm.get("claims", []), start=1):
            key = (blind_id, clean_text(claim.get("text")))
            occurrence = occurrence_counts[key]
            occurrence_counts[key] += 1
            evidence_name = f"claim-{ordinal:02d}-{claim_index:02d}-{claim['claim_id']}.md"
            evidence_path = EVIDENCE_DIR / evidence_name
            write_evidence_file(
                evidence_path,
                blind_id,
                claim,
                report_digest,
                snapshot_digest,
                claim.get("source_records", []) or [],
                scope,
            )
            entries.append(
                {
                    "ordinal": len(entries) + 1,
                    "arm_ordinal": ordinal,
                    "blind_id": blind_id,
                    "claim_index": claim_index,
                    "claim": claim,
                    "report_window": report_window(report, clean_text(claim.get("text")), occurrence),
                    "evidence_name": evidence_name,
                    "scope": scope,
                    "status_flags": evidence_status(claim, claim.get("source_records", []) or [], scope_by_index(scope)),
                    "snapshot_digest": snapshot_digest,
                }
            )

    assert len(entries) == 48, len(entries)
    lines = [
        "# Blinded independent review sample: 48 claims",
        "",
        "## Purpose",
        "",
        "This README presents the preserved stratified sample of 48 claims awaiting independent biomedical review. It gives a reviewer the exact blinded claim text, report context, the citations and source material that were supplied to the system, and blank fields for an independent assessment. It does not contain verdicts and does not replace the preserved packet or source snapshots.",
        "",
        "The sample was drawn from the preserved 446-claim blinded packet. The packet contains the remaining claims and is the authoritative record for claims outside this sample: [full blinded packet (446 claims)](../archive-claim-review-packet-20261112.json). The preserved sample manifest is [here](../archive-claim-review-sample-20261112.json). The separate blind-ID/arm mapping remains outside this README.",
        "",
        "## How to review",
        "",
        "For each claim, choose one verdict: **supported**, **partially supported**, **unsupported**, **contradicted**, or **unverifiable**. Use the exact supplied source passages and the stated reading scope. A scientific assertion is a statement about biology, methods, data, effects, or conclusions. A statement about a limitation of the supplied material (for example, that an impact factor or full Methods section was not supplied) describes what was available to the research process; it is not by itself a scientific assertion about the underlying study. Reviewers may record uncertainty and should mark a claim unverifiable rather than guess when the supplied evidence is insufficient.",
        "",
        "A verdict on this 48-claim sample cannot establish an overall hallucination rate. Independent semantic review, source access, and reviewer agreement are separate limitations; a generated README is not a completed review.",
        "",
        "## Evidence flags",
        "",
        "The flags below are mechanical availability notes from the preserved artifacts. They do not pre-judge the claim. **Abstract-only access** means the preserved reading scope identifies an abstract-level view. **Abstract-plus-excerpts access** means an abstract and selected excerpts were supplied, without establishing complete full-text coverage. **Missing evidence** means no source passage was attached in the preserved packet. **Unresolved citation** means a citation index did not resolve to a supplied source record. Reviewers may still use public links to locate the work if their protocol permits, but should record that this is outside the supplied material.",
        "",
    ]
    render_external_disagreements(lines)
    render_human_adjudication(lines)
    lines.extend(["## Sampled claims", "",])

    for entry in entries:
        claim = entry["claim"]
        blind_id = entry["blind_id"]
        lines.extend(
            [
                f"### Sample {entry['ordinal']:02d} — `{blind_id}` / claim `{claim['claim_id']}`",
                "",
                f"- **Blind report ID:** `{blind_id}`",
                f"- **Claim kind recorded in packet:** `{clean_text(claim.get('kind')) or 'not supplied'}`",
                f"- **Citation indices recorded:** {', '.join(f'`[{clean_text(x)}]`' for x in claim.get('citations', [])) if claim.get('citations') else 'none'}",
                "",
                "#### Exact claim text",
                "",
                fence(clean_text(claim.get("text")), "text"),
                "",
                "#### Surrounding report context",
                "",
            ]
        )
        sample_context = clean_text(claim.get("context"))
        if sample_context:
            lines.append("Context recorded with the sampled claim:")
            lines.append(fence(sample_context, "markdown"))
            lines.append("")
        window = entry["report_window"]
        if window:
            lines.append("Mechanical report window from the preserved report (near the exact occurrence; not a semantic rewrite):")
            lines.append(fence(window, "markdown"))
        else:
            lines.append("No exact textual occurrence was found in the preserved report string; consult the full packet linked above.")
        lines.extend(["", "#### Supplied citations and evidence", ""])
        sources = claim.get("source_records", []) or []
        if not sources:
            lines.append("No source record is attached to this claim in the preserved sample.")
        else:
            scope = scope_by_index(entry["scope"])
            for source in sources:
                lines.extend(render_source_metadata(source, scope))
                texts = source_texts(source)
                if texts:
                    # Keep the README readable while linking the complete passage below.
                    excerpt = texts[0][1].strip()
                    if len(excerpt) > 900:
                        excerpt = excerpt[:900].rstrip() + "…"
                    lines.append("  - Supplied evidence excerpt (start of the recorded passage; complete text is linked below):")
                    lines.append(f"    {fence(excerpt, 'text').replace(chr(10), chr(10) + '    ')}")
                else:
                    lines.append("  - No abstract or full-text passage is supplied in this source record.")
        lines.append(f"- **Complete supplied evidence and per-source reading scope:** [local evidence file](evidence/{entry['evidence_name']})")
        flags = entry["status_flags"]
        lines.append("- **Availability flags:** " + ("; ".join(flags) if flags else "No mechanical availability flag recorded."))
        lines.extend(
            [
                "",
                "#### Independent reviewer fields",
                "",
                "- **Reviewer verdict (supported / partially supported / unsupported / contradicted / unverifiable):** ",
                "- **Supporting quotation:** ",
                "- **Explanation:** ",
                "",
                "---",
                "",
            ]
        )

    README_PATH = OUT_DIR / "README.md"
    README_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "archive_claim_review_readme.v1",
        "status": "presentation_only_unlabeled",
        "sample_path": "../archive-claim-review-sample-20261112.json",
        "packet_path": "../archive-claim-review-packet-20261112.json",
        "sample_sha256": sha256(SAMPLE_PATH),
        "packet_sha256": sha256(PACKET_PATH),
        "claim_count": len(entries),
        "evidence_file_count": len(list(EVIDENCE_DIR.glob("claim-*.md"))),
        "entries": [
            {
                "ordinal": e["ordinal"],
                "blind_id": e["blind_id"],
                "claim_id": e["claim"]["claim_id"],
                "claim_text_sha256": hashlib.sha256(clean_text(e["claim"].get("text")).encode("utf-8")).hexdigest(),
                "evidence_file": f"evidence/{e['evidence_name']}",
            }
            for e in entries
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "built", "readme": str(README_PATH), "claims": len(entries), "evidence_files": manifest["evidence_file_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
