# Earlier cited-source recovery — 2026-11-11, undeployed

The candidate repairs two source-availability failures without interpreting scientific meaning: refetching a known source after a collector reset did not return it to the current call, and finalization ignored previously collected sources explicitly cited by a draft when no new results were present. It preserves sources and unresolved labels. This is not a measured reduction in scientific hallucination.

## Diagnosis and fixture correction

Preserve the current 159-file application/deployment/test tree before editing, including all earlier candidates. Then correct the shared test fixtures:

- Compose the AST collector with the same `SourceCollectionMixin` installed by `install_overlays.py`.
- Keep the raw acquired-text-in-writer assertions, and check the actual abstract/body artifact contract: untyped fetched text remains available but cannot silently become a full-paper artifact. The previous test dereferenced a missing artifact slot.
- Use the actual installed `LangGraphAgentStrategy._finalize`, with explicit recording/no-network adapters, rather than an incomplete AST namespace/fake runner.
- Supply the PubMed XML fixture's primary `MedlineCitation/Article/Abstract` hierarchy and current proxy/error helper dependencies; retain its exact nested-text/negation assertions.

Against the frozen baseline, corrected shared fixtures produce **76 passed, two failed**. The remaining failures are refetch-to-current-call restoration and earlier-cited-source recovery. Thus the previous five failures were not all fixture defects. Initial logs and the prior five-failure triage remain preserved; no failed test was deselected or marked successful merely because baseline also failed.

## Runtime change

`SourceCollectionMixin._merge_duplicate` already runs under the collector lock. It now restores the merged existing record and URL to the current call if absent, keeping its original index and one accumulated record. This covers both search reuse and fetch-tool `find_or_add_result`; it does not allocate another citation identity or discard acquired text.

The new `sources_for_draft` helper keeps every current result and adds copies of previously accumulated records only for explicit prose citation indices. It uses the existing code/bibliography-aware citation parser and `SourceLookup`; it performs no title matching, query-keyword parsing, relevance filtering, network request or scientific inference. Recovered copies do not mutate the archive or pretend to be newly retrieved results. No archive-wide source expansion occurs, and existing native material budgets remain in force.

Differing supplied records sharing an index remain ambiguous; absent indices remain missing. These states do not delete a current record, invent a replacement source, remove a draft claim or prevent publication. Unreferenced archive records stay in the archive. The lookup's `resolved` status means index resolution only, never entailment or scientific validation. Exact repeated records do not create ambiguity, but differing metadata can conservatively leave an index ambiguous even if the records might describe the same paper; no fuzzy merge is introduced.

`_finalize` uses the current-plus-recovered set for its existing writer path and returned source metadata/URLs. Its final-report metadata includes the lookup scope and requested/recovered/missing/ambiguous IDs. This can activate native synthesis on a call that previously skipped it; real model cost and latency may increase. Existing source-reading/consistency behavior is retained, save-time citation audits remain off, and `GROUNDING_INSTRUCTIONS` bytes are unchanged. No new prompt rules or production configuration changes are introduced.

Runtime changes are limited to `langgraph_agent_strategy.py`, `research_verify/source_collection.py`, and a read-only `SourceLookup.ambiguous_indices` property in `research_verify/evidence.py`. [The 313-line patch](../evaluation/source-recovery-candidate-20261111.patch) includes those changes, corrected fixtures and new routing checks; forward/reverse apply checks pass against the frozen trees. Patch SHA256: `518901ae86de6f7473e8fe9b5749171610ece16b684a5a2142861e085be14771`. No new branch or commit is created.

## Frozen component comparison

Before runtime edits, freeze 16 routing cases and settings: 12 previously inspected real-source development cases (medicine, biology, bioinformatics and a forest-carbon control; direct/paraphrase/adversarial variants), plus four missing/ambiguous/code/bibliography controls. Sources are archived Europe PMC records with original acquired abstracts. Drafts are synthetic routing placeholders, not generated scientific reports. Expected source IDs are implementing-agent contracts, not independent relevance/entailment labels. See [baseline freeze](../evaluation/source-recovery-freeze-20261111.json) and [case freeze](../evaluation/source-recovery-cases-freeze-20261111.json).

Install each frozen arm in disposable network-disabled containers using the same application image. Execute actual installed finalization, native document construction/material formatting, the actual collector refetch path, and publication mapping. A recording writer preserves the draft while exposing its input sources; annotation/network adapters do no external work. Native model reading, writing and consistency checking are not executed. Save-time QC is explicitly disabled for the publication probe. Both arms receive identical current records, archives, drafts, settings and questions. Source exposure deliberately differs as the behavior under test.

| Endpoint | Baseline | Candidate |
|---|---:|---:|
| Prior cited source and complete supplied abstract exposed to writer | 0/12 | 12/12 |
| Correct prior-source URL in publication mapping | 0/12 | 12/12 |
| Current records preserved | 16/16 cases, eight nonempty | 16/16 cases, eight nonempty |
| Draft, current collector and archive unchanged by finalization probe | 16/16 | 16/16 |
| Controls without archive expansion | 4/4 | 4/4 |
| Missing/ambiguous labels retained without guessed URL | 6/6 observations | 6/6 observations |
| Recording-handler activations | 8 | 12 |
| Real model / live network calls during probes | 0 / 0 | 0 / 0 |

Each development domain has three prior-source observations: 0/3→3/3 for exposure and binding. These are mechanical source-routing results, not representative domain-regression or hallucination rates. Baseline lacks the new lookup metadata; its absence is unreported and is not scored as a semantic failure. Exposure is measured from actual supplied records/abstracts, rather than newly added fields.

The actual installed refetch probe returns index 1 in both arms and retains the original abstract/new fetched text in one accumulated record. Baseline current source/URL counts are zero; candidate counts are one. This confirms the installed collector behavior independently of the AST test seam.

Finalization/material/publication component time averages roughly 1.6 ms baseline and 2.4 ms candidate in this single offline run. Installation/imports and model work are excluded. This is not research latency or a model-cost estimate; four extra writer-path activations are a real potential cost to measure in a future native-model comparison.

## Validation and remaining evidence

Candidate tests: **90 passed**: the 78 shared corrected-fixture checks, eight new recovery checks and four existing collector checks. Assertions cover exact acquired text, ID reuse, source availability, unresolved-label preservation, code/bibliography exclusions, no collector/archive mutation, concurrency reuse and native document/material processing. Frozen code/input manifests and original corrected-fixture hashes are checked. Initial probes before publication mapping were preserved before extending the common probe. [Results and denominators](../evaluation/source-recovery-results-20261111.json), [probe](../scripts/probe_source_recovery.py), [collector](../scripts/collect_source_recovery.py). Private snapshots/logs/raw outputs remain under `/data1/maxw/ldr-evaluation/source-recovery-20261111/`.

These checks do not establish citation entailment, unsupported/contradicted-claim rates, useful synthesis, recommendation quality, retrieval recall, real-model latency or representative cross-domain robustness. The prior 16-pair report-generation comparison contains older code. No scientific assessment was performed here; all such endpoints remain unmeasured, rather than counted as successes. The literature-inspired selector/revision hypotheses remain proposals, and overall reliability improvement remains unproven.

No 5000/5002 deployment/restart, production model/source-pool change, historical report modification or production dependency installation occurred. Temporary probe/test containers exited. Further work includes authoritative identity/publication-state provenance and independently assessed native report comparisons, with fresh frozen sources/tasks before tuning.
