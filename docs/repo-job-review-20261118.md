# Repository job review and evidence-integrity improvements — 2026-11-18

## Scope and conclusion

Reviewed the current handoff, active research flow, baseline/roadmap, saved six-task diagnostics, existing independent reviews, matched evaluation receipts, deployment mapping and the evidence/writer/publication paths. Fetched origin: local HEAD is `5a1e2a0`; `origin/main` is `49501d0`, one commit ahead. No merge, production restart, model call or deployment was performed. Existing worktree changes were preserved.

The reproducible [inventory](../evaluation/repo-job-review-20261118/inventory.json) covers every `rg --files --hidden` visible `report.md` and `summary.json`, plus direct baseline/candidate JSON receipts with supported job schemas. Private labels and blinded-review copies are excluded. This is **saved-artifact coverage**, not a claim to inspect every scientific assertion, remote database job, arbitrary filename or live service. Summary files and repeated runs are not independent scientific cases.

Found 109 saved generation outputs, 10 summaries and six research reports. Generation completeness is 48 explicit normal stops, 13 explicit token cutoffs and 48 unknown because a finish reason was not recorded. All 13 truncated receipts nevertheless say `completed`; the 48 unknown receipts also say `completed`, but unknown does not prove truncation. No parser errors occurred.

The newest 12,000-token diagnostic receipts have one cutoff in each six-question arm, both on D01 (immune). The 18-case 12,000-token arms have no recorded cutoff. Completion is a transport property and does not establish factual accuracy. The older external AI review found no clear error-rate advantage; its cohort-scope interpretation was itself disputed in the handoff. No corrected-claim score is assigned here.

## Six full research jobs

Counts below were recomputed with the shared Markdown citation parser; reference labels and code do not count as prose citations. The source counts describe collected records, not confirmed eligible papers.

| Task | Collected records | Cited IDs | Uncited records | Missing/ambiguous cited IDs |
| --- | ---: | ---: | ---: | ---: |
| Immune | 28 | 14 | 14 | 0 |
| RNA QC | 18 | 4 | 14 | 0 |
| Tumor / 20 papers | 80 | 15 | 65 | 0 |
| Diabetes | 53 | 41 | 12 | 0 |
| Adipose | 59 | 20 | 39 | 0 |
| Xenium | 80 | 80 | 0 | 0 |

Zero missing IDs establishes structural linkage only. It does not establish identity, eligibility, relation accuracy or support.

The existing [source audit](../evaluation/frontier-strategy-20261113/local-ds41-feedback-original-prompts-20261117T141028Z/offline-source-audit.json) flags mixed publication types in every pool, metadata-only records in tumor/diabetes/adipose/Xenium, and topic risks in adipose/Xenium. Those are diagnostic flags; reviews, protocols and preprints may legitimately be useful background. No keyword flag authorizes deletion or proves a hallucination.

The earlier independent [handoff](../README.md) identifies distinct mechanisms: acquired method passages omitted before writing; scientific relation terminology misinterpreted; candidate counts promoted to eligibility counts; source identity/type confused with journal identity; and partial attribute checks accepted as full support. These require separate evaluation. Additional prompt instructions alone have not demonstrated a general improvement.

## Implemented fixes

1. `evidence_grounding.py` uses the shared source lookup ambiguity policy. Different records with the same citation index remain unresolved; they are retained in candidate counts and flagged rather than silently choosing the first record. Ambiguous enrichment records cannot overwrite review-document material.
2. Positive detector verdicts become `unverifiable` in the ledger when a cited record is missing/ambiguous, cited text is unavailable, or no exact evidence locator can be bound. The original detector verdict/reason remains separately recorded. This changes advisory metadata, not the report body.
3. Exact locators require the correct citation ID, literal source field, offsets, quote and content hash. They accept both serialized dictionaries and model objects. An absent field cannot silently fall back to an abstract/body under a false field name. Boolean IDs/offsets are rejected. A located quote remains necessary evidence provenance, not sufficient semantic entailment.
4. `generation_receipt.py` separates complete, truncated, empty and unknown output. Future held-out runs retain partial output but label it `incomplete`, count it separately from API failures, and do not label the whole protocol complete when any output is incomplete. Historical receipts are untouched; the new inventory interprets their observable state separately.
5. `scripts/review_saved_jobs.py` records artifact hashes, completion evidence and report/source linkage without a model or network. It is an explicit audit command, not a periodic monitor.

These fixes reduce false confidence and evidence misbinding. They do **not** establish a reduction in scientific hallucinations. Save-time citation QC remains off; native consistency checking and production model/source settings are unchanged. No publication gate, automatic report deletion or topic-specific runtime rule was added. Deployable module changes are under `local_deep_research/research_verify/`, which the installer copies as a package; runner and audit scripts are local tooling.

## Validation and remaining work

- Focused grounding, job-review, generation and evidence-flow tests: **98 passed, one deliberately deselected**. The deselected test imports `local_deep_research.advanced_search_system`, unavailable with this checkout's local test import path; the initial full focused run reproduced that import failure. [JUnit receipt](../evaluation/repo-job-review-20261118/focused-tests.xml).
- Broader run including publication and citation-evidence suites: **130 passed, 39 failed, one deselected** before the final added regression. Failures include audit-enabled expectations despite the current default being off, obsolete `ClaimCheck.citation_checks` access, exporter code assumptions and upstream runtime imports. This is not a green full-suite result. Current user audit settings were preserved.
- Changed modules compile; `git diff --check` passes. Inventory rerun produced the same artifact counts with no read/parse errors.
- No fresh model generation, human adjudication or live pipeline quality test was performed. No new hallucination-reduction percentage is claimed.

Next priorities: reconcile legacy tests with current advisory/default contracts, then assess source-first method delivery at the actual writer boundary and compare full relation attributes across matched reports. Keep six-task regressions separate from frozen held-out acceptance, preserve useful requested content, and score omissions, source eligibility, bibliographic mistakes, unsupported assertions and new errors separately. Repeating the same writer with longer instructions is not sufficient evidence of improvement.

Reproduce the inventory:

```bash
PYTHONPATH=local_deep_research python scripts/review_saved_jobs.py \
  --output evaluation/repo-job-review-20261118/inventory.json
```
