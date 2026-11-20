# Explicit intent and unknown-state candidate

This development candidate removes semantic assertions made from substrings in research questions. It is not deployed. Production models, three search sources, 5000/5002, native fact consistency and the disabled save-time citation audit remain unchanged.

## Behavior and tradeoff

`ResearchSpec` no longer infers publication language/dates, requested paper count, fields, task mode or protocol intent from question words. The original question still reaches the agent/writer. Missing intent stays unknown and contributes no generated scope instruction block. Explicit `report.*` settings are validated, retain provenance and remain available for field preparation and writing. Invalid settings remain unresolved. Literal IF comparison syntax can be recorded as deferred metadata; it does not enable filtering.

The second `ConstraintMatcher` query parser and its automatic LLM fallback are removed too. It accepts structured scope settings, records unknown input intent, keeps missing source metadata pending, and honors strict/inclusive/equality operators in explicit legacy IF diagnostics. Runtime IF remains deferred. Unknown source language/year can no longer create a green condition badge.

Keyword coverage requires explicit terms. Query tokenization/stop-word semantics and model guesses are removed. The annotation states lexical overlap and `semantic_assessment=not_performed`; badges show hit counts rather than scientific relevance or satisfaction. Long untyped content is not automatically classified as full text. No source/report text is removed, and no publication gate is added.

This intentionally removes automatic planning hints and extra field preparation triggered by guessed intent. The ordinary writer still reads the question and native supplied-source material. It could lose useful field-extraction assistance, so false-metadata reduction alone cannot validate the change. Explicit structured controls are programmatic tests; no new end-user settings UI is claimed.

The archived feedback inspector no longer assigns a topic-specific semantic pass or silently skips the KRAS prompt. It records prompts/feedback with stable IDs and reports `not_performed`. The synthetic output-contract script now uses explicit settings and reports structural-only status. Historical reports and past results are unchanged.

## Prospective comparison

Before the new runtime edits, the full current baseline (157 files), experiment and source bytes were frozen in `/data1/maxw/ldr-evaluation/intent-paired-20261110/`. This baseline includes earlier source-state changes and the PubMed implicit-date fix; it is not the original pre-literature baseline. Eight real Europe PMC MED records form four packs, each with two topic papers and one distractor: corticosteroids, programmable genome editing, differential-expression methods and forest carbon. An initial incorrect remembered PMID resolved to an unrelated food-science article and was replaced using the DOI record **before freezing**; it is not included in the source packs. Raw lookup evidence is retained.

The sixteen cases comprise direct, paraphrased, adversarial and explicit-settings positive controls in each family. Twelve cases concern medicine/biology/bioinformatics and four are climate controls. Tasks, packs, obligations, rubric and hypothesis were frozen before editing. This is a prospective fixed evaluation visible to the implementer, not a sealed or representative held-out sample, and it has no independent expert gold. The original 24-case scaffold remains a scaffold.

The runner invokes the actual `LangGraphAgentStrategy._finalize`, native source reading/writing/fact checking and publication metadata in disposable containers. Common adapters close supplementary evidence fetching and disable external DOI checks; UI progress/formatting are bypassed. Save-time QC is off. This tests finalization with fixed sources, not planning, live retrieval, full end-to-end research or production behavior. There is one generation per arm; first-arm order alternates by case, with at most two generation containers active. Failures and all calls/traces remain recorded.

The initial candidate smoke is stored under `smoke-candidate` and excluded from paired outputs. Frozen candidate code and copied runner files are used for the comparison. A separate installed detailed-report test found missing optional settings fell through to thread-local context. The development detailed adapter now reads/unwraps its explicit snapshot with unknown defaults; the frozen ordinary-finalization candidate remains unchanged. That correction has integration tests, not a detailed-report quality comparison. Its code difference must remain explicit in the final record.

## Validation boundaries

Forty-six focused tests passed after the detailed adapter correction, including strict IF boundaries, explicit settings precedence, unknown source metadata, model-free query parsing, lexical evidence scope and installed detailed-report snapshot behavior. The first detailed integration attempt failed; its log is retained. Existing semantic-parser expectations were updated to the new explicit-settings contract, not counted as scientific improvement.

The first 32-report generation completed, but source review found the evaluation preparation's `<[^>]+>` tag-stripping regex swallowed scientific `P<...` comparisons and following result text. Two medical records lost 685/863 characters; their use as distractors affected three source packs. Raw API bytes remain intact. The first run is marked invalid for the intended complete-abstract comparison, not erased or retroactively described as a deliberately excerpted task. Relative preservation against a faulty pack was insufficient validation.

Corrected packs use an HTML parser; literal comparison text and nested text/tails are checked. All 32 reports were regenerated under a new frozen experiment in `/data1/maxw/ldr-evaluation/intent-paired-corrected-20261110/`, using unchanged questions, semantic candidate, rubric and model settings. This is a data-integrity correction, not tuning the writer to the observed answers. The old run's scope assumptions cannot establish source completeness, hallucination reduction or absence of subgroup results. The production Europe PMC helper already uses HTMLParser; the faulty regex was in the evaluation preparation, not evidence of that runtime bug.

## Corrected-run observations

All 16 baseline and 16 candidate reports completed on matched source/model/settings hashes. Source snapshots were preserved in 16/16 reports on each side. All 872 recorded trace payloads passed byte/SHA checks; every report had a native-check request (27 baseline requests, 24 candidate, because checks can be batched). Invocation does not imply correct verification.

| Quantity | Baseline | Frozen intent candidate |
|---|---:|---:|
| Completed generations / scheduled | 16/16 | 16/16 |
| Valid assisted annotations / scheduled | 9/16 | 11/16 |
| Invalid annotations retained | 7 | 5 |
| Labelled empirical units, valid reports only | 128 | 169 |
| Model-labelled supported / labelled units | 121/128 | 163/169 |
| Model-labelled unsupported / labelled units | 1/128 | 0/169 |
| Model-labelled contradicted / labelled units | 0/128 | 0/169 |
| Unverifiable after quote validation | 6/128 | 6/169 |
| Citation-entailing / available labels | 119/124 | 163/164 |
| Missing entailment labels in valid reports | 4 | 5 |
| Covered frozen obligations / scheduled | 45/80 | 55/80 |
| Missing obligation labels | 35 | 25 |
| Mean model-rated usefulness, available reports | 5.0/5, n=9 | 5.0/5, n=11 |
| Total generation model calls | 73 | 56 |
| Automatic constraint-inference calls | 14 | 0 |
| Reading / writing calls | 16 / 16 | 16 / 16 |
| Input / output tokens, all recorded calls | 165,311 / 74,966 | 151,480 / 65,650 |
| Mean finalization latency | 36.75 s, n=16 | 32.35 s, n=16 |

The claim denominators exclude **unknown units in invalid reports**; they do not imply full annotation coverage. Nine of sixteen pairs have valid annotation on both sides: direct 3/4, paraphrase 2/4, adversarial 2/4 and structured controls 2/4. Invalidity is asymmetric and could bias the apparent difference. Nine invalid annotations failed strict claim-substring/schema validation and three had unparseable JSON/schema. Raw responses remain; no post-hoc label recovery, prompt adjustment or output filtering was applied.

The only model-labelled unsupported unit is a forest report's interpretation that climate-driven canopy loss undercuts the sweeping premise. Implementer review disputes treating that reasoning as an empirical hallucination: the source explicitly projects climate-driven loss. Conversely, the candidate biology report's `in vitro`/`cultured` qualifiers were labelled supported despite not being established by the supplied abstracts. The baseline biology report also adds an unestablished `in vitro` qualifier, and its automatic annotation was invalid. These are source-relative scope concerns, not assertions that external scientific facts are false. Thus the numerical 1→0 labels **do not establish an error-rate reduction**.

All eight preselected adversarial reports received source-relative implementer review with arm labels withheld during initial notes, then unblinded. Both medical reports preserve the restored subgroup estimates/intervals; all eight retain useful findings while rejecting sweeping premises. One RNA-seq proposal uses agreement/stability without a clear ground-truth accuracy criterion, while the other explicitly proposes spike-ins/validated truth. Bounded recommendations are assessed for usefulness, not counted automatically as factual hallucinations. This is AI implementer review, not independent human gold.

Calls and tokens are directly recorded. Removing the automatic intent inference accounts for 14 calls; the remaining three-call difference comes from native-check batching/output variability, not removal of fact consistency. The observed mean latency difference is −4.40 s; a four-family bootstrap is −6.45 to −1.97 s. This single-run interval does not model server load, repeated-run variation or production latency, and no causal overall speedup is established. Monetary cost is not estimated.

Per-domain quality comparisons have only one task family each; bootstrap intervals are unavailable. Validly assessed matched pairs are medicine 3, biology 3, bioinformatics 1 and climate 2. No robustness conclusion follows from this sparse, selected subset. Detailed per-domain/variant results and raw denominators are in `evaluation/intent-paired-results-20261110.json`; source review and annotation diagnostics are in the private corrected-run directory. `evaluation/intent-final-artifacts-20261110.json` records artifact hashes.

The metadata behavior changed as intended: the baseline creates a 2012–2013 publication scope even where the genome-editing query explicitly says those years identify studies rather than filter publications; the candidate leaves the scope unknown. It no longer treats `stable` as a table request. Explicit controls retain requested fields/count through settings. Those observations establish metadata behavior, not report quality or absence of extraction regressions.

Effectiveness remains unproven. Retrieval was measured separately in the earlier three-engine pilot; source preservation here cannot be called search recall. Wider independent domains, longer evidence packs/full-text cases and independent annotations remain necessary for a representative reliability claim.
