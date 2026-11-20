#!/usr/bin/env python3
"""Run one bounded claim-planner/verifier/reconciliation mechanism check.

This is an evaluation receipt producer, not a production path.  It sends three
small calls to the configured OpenAI-compatible gateway: a claim-specific
question planner, a source-only answerer, and a separate reconciliation call.
All prompts and raw responses are retained so parse failures remain visible.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/frontier-strategy-20261113/planner-check-v2-20261113"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "local_deep_research"))
from research_verify.independent_verification import (  # noqa: E402
    ClaimPlanningInput,
    SourcePassage,
    build_claim_reconciliation_prompt,
    build_question_planning_prompt,
    build_verification_prompt,
    parse_claim_reconciliation_response,
    parse_verification_response,
    plan_verification_questions,
)


ENDPOINT = os.environ.get("LDR_LLM_OPENAI_ENDPOINT_URL", "http://27.30.76.162:6183/v1").rstrip("/")
API_KEY = os.environ.get("LDR_LLM_OPENAI_ENDPOINT_API_KEY", "")
MODEL = os.environ.get("LDR_LLM_MODEL", "deepseek-v4-flash")
TEMPERATURE = 0
MAX_TOKENS = 2500


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_gateway(prompt: str) -> dict[str, Any]:
    """Make one bounded non-streaming chat call and retain transport metadata."""
    started = time.monotonic()
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }
    try:
        response = requests.post(
            f"{ENDPOINT}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        elapsed = time.monotonic() - started
        body_text = response.text
        try:
            body = response.json()
        except Exception:
            body = None
        content = ""
        finish_reason = None
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices and isinstance(choices[0], dict):
                finish_reason = choices[0].get("finish_reason")
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "elapsed_seconds": round(elapsed, 3),
            "finish_reason": finish_reason,
            "prompt_sha256": sha_text(prompt),
            "prompt_chars": len(prompt),
            "response_sha256": sha_text(content or body_text),
            "content": content,
            "response_body": body,
            "transport_error": "",
        }
    except Exception as exc:  # preserve failures instead of manufacturing answers
        return {
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "finish_reason": None,
            "prompt_sha256": sha_text(prompt),
            "prompt_chars": len(prompt),
            "response_sha256": "",
            "content": "",
            "response_body": None,
            "transport_error": f"{type(exc).__name__}: {exc}",
        }


def invoke_and_record(name: str, prompt: str) -> dict[str, Any]:
    call = call_gateway(prompt)
    (OUT / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    (OUT / f"{name}.response.txt").write_text(call.get("content") or "", encoding="utf-8")
    (OUT / f"{name}.transport.json").write_text(
        json.dumps({k: v for k, v in call.items() if k not in {"content", "response_body"}},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return call


def main() -> int:
    source_record = json.loads(
        (ROOT / "evaluation/frontier-strategy-20261113/production-trace-check.json").read_text()
    )["cases"]["diabetes"]["selected_events"][0]["source_101"][0]
    source_text = source_record["abstract"]
    source = SourcePassage(
        source_id=101,
        title=source_record["title"],
        identity={"pmid": source_record["pmid"], "doi": source_record["doi"], "url": source_record["link"]},
        text=source_text,
        field="abstract",
        basis="preserved production trace abstract",
        scope_note="Original paper abstract only; no full-text methods were supplied to this check.",
    )
    claims = (
        ClaimPlanningInput(
            "claim-7f3a",
            "AKT1、CASP9和EIF2S1被确定为候选坏死性凋亡相关基因。",
            (101,), "body", "糖尿病周围神经病变综述；机制分类与候选基因结论。", 0, 36,
        ),
        ClaimPlanningInput(
            "claim-b2c1",
            "AKT1、CASP9和EIF2S1被三种机器学习方法共同优先排序。",
            (101,), "body", "同一段落中的候选基因筛选方法与结果。", 37, 74,
        ),
        ClaimPlanningInput(
            "claim-9d84",
            "该研究使用LASSO、SVM-RFE和随机森林优先排序候选基因。",
            (), "body", "同一来源的无显式引用方法陈述，用于检查未引用claim是否保留。", 75, 101,
        ),
    )
    (OUT / "claims.json").write_text(json.dumps([c.__dict__ for c in claims], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "source-pack.json").write_text(json.dumps({"sources": [source.__dict__]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    calls: dict[str, Any] = {}
    planner_prompt = build_question_planning_prompt(claims, max_claims=3)
    calls["planner"] = invoke_and_record("01-planner", planner_prompt)
    planner_raw = calls["planner"].get("content", "")
    planning: dict[str, Any] = {"status": "unparsed", "raw_sha256": sha_text(planner_raw), "error": ""}
    questions = ()
    links = ()
    try:
        result = plan_verification_questions(lambda _prompt: planner_raw, claims, max_claims=3, max_questions=6)
        questions, links = result.questions, result.links
        planning = {
            "status": "parsed",
            "prompt_sha256": result.prompt_sha256,
            "candidate_claim_ids": result.candidate_claim_ids,
            "planned_claim_ids": result.planned_claim_ids,
            "uncovered_claim_ids": result.uncovered_claim_ids,
            "budget_limited_claim_ids": result.budget_limited_claim_ids,
            "parse_warnings": result.parse_warnings,
            "questions": [q.__dict__ for q in questions],
            "links": [dict(x) for x in links],
        }
    except Exception as exc:
        planning["error"] = f"{type(exc).__name__}: {exc}"
    (OUT / "planner-result.json").write_text(json.dumps(planning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verification: dict[str, Any] = {"status": "not_run", "answers": [], "error": ""}
    answers = ()
    if questions:
        verification_prompt = build_verification_prompt(questions, (source,))
        calls["answerer"] = invoke_and_record("02-answerer", verification_prompt)
        answer_raw = calls["answerer"].get("content", "")
        try:
            answers = parse_verification_response(answer_raw, questions, (source,))
            verification = {
                "status": "parsed",
                "questions": [q.__dict__ for q in questions],
                "answers": [a.__dict__ | {"evidence": [e.__dict__ for e in a.evidence], "evidence_status": a.evidence_status, "effective_status": a.effective_status} for a in answers],
            }
        except Exception as exc:
            verification = {"status": "parse_failed", "error": f"{type(exc).__name__}: {exc}", "answers": []}
    else:
        verification["error"] = "no_valid_planned_questions"
    (OUT / "answerer-result.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reconciliation: dict[str, Any] = {"status": "not_run", "comparisons": [], "error": ""}
    if answers:
        reconciliation_prompt = build_claim_reconciliation_prompt(claims, answers, links)
        calls["reconciliation"] = invoke_and_record("03-reconciliation", reconciliation_prompt)
        recon_raw = calls["reconciliation"].get("content", "")
        try:
            comparisons = parse_claim_reconciliation_response(recon_raw, [c.claim_id for c in claims])
            reconciliation = {"status": "parsed", "comparisons": list(comparisons)}
        except Exception as exc:
            reconciliation = {"status": "parse_failed", "error": f"{type(exc).__name__}: {exc}", "comparisons": []}
    else:
        reconciliation["error"] = "no_parsed_answers"
    (OUT / "reconciliation-result.json").write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "schema_version": "planner_check.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": MODEL,
        "endpoint_base": ENDPOINT,
        "settings": {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "calls_planned": 3},
        "claims": [c.claim_id for c in claims],
        "source_id": 101,
        "source_identity": source.identity,
        "planner": planning,
        "answerer": verification,
        "reconciliation": reconciliation,
        "call_receipts": {k: {key: value for key, value in v.items() if key not in {"content", "response_body"}} for k, v in calls.items()},
        "interpretation": {
            "status": "mechanism_diagnostic_only",
            "relation_error_target": "paraptosis_in_source_vs_necroptosis_in_claim",
            "useful_content_retention": "unresolved_without_independent_semantic_adjudication",
            "hallucination_reduction_claim": False,
            "limitations": [
                "One source and three claims cannot establish generalization or a hallucination-rate change.",
                "The source is an abstract; missing full-text details remain unknown.",
                "A model-selected quote is only a located passage, not entailment proof.",
            ],
        },
    }
    (OUT / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "planner": planning.get("status"), "answerer": verification.get("status"), "reconciliation": reconciliation.get("status"), "calls": list(calls)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
