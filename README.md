# Astro DRA

![Astro DRA banner](assets/banner.png)

Astro DRA is a research assistant built on [Local Deep Research](https://github.com/LearningCircuit/local-deep-research). It combines literature search, evidence collection, source-aware writing, and report publication in a Docker deployment. Models can be connected through an OpenAI-compatible endpoint.

The current source pool is **PubMed, SearXNG, and Europe PMC**. The system preserves source identity, abstracts, selected full-text context, and private research traces so that generated reports can be inspected later.

## Active hallucination-reduction handoff (2026-11-13, 13:16 CST)

This section is for the Codex taking over the active work. **The objective is still open:** reduce a strict majority of the original feedback's hallucination and evidence problems in a way that generalizes across tasks. Do not report success from tests, retrieval recall, model consensus, or a single question. The frozen inventory has **6 tasks, 34 primary allegations, and 38 stress-expanded units**; strict majority thresholds are 18/34 and 20/38. The allegations mix factual errors, bibliographic identity, scope, omissions, duplicates, and unresolved cases, so the denominator is not a count of confirmed hallucinations. No candidate correction has yet been credited. See the [frozen inventory](evaluation/pane2-independent-review-20261113/full-feedback-issue-inventory.json) and [category accounting](evaluation/pane2-independent-review-20261113/full-feedback-category-accounting.json).

Start by reading [AGENTS.md](AGENTS.md), this handoff, [current research flow](docs/current-research-flow-20261016.md), [current status](docs/current-status.md), and [roadmap](docs/roadmap.md). **Recovery warning:** at 13:19 CST an unrelated Pane 2 note-update script accidentally overwrote the uncommitted full [development progress](docs/development-progress.md) with a 108-line review note. That exact overwritten state is preserved [here](evaluation/pane2-independent-review-20261113/development-progress-overwrite-state-20261113.md); the full pre-overwrite working copy has not been found, so the current progress file is incomplete. Earlier committed history remains available through `git show HEAD:docs/development-progress.md` and other dated docs. Treat this README and the linked immutable receipts as the current handoff, not the damaged progress file. Recheck `git status` and `git fetch origin` before editing. At this handoff, HEAD and `origin/main` both equal `5a1e2a04ec50f9a1b193db22b25db2b6bcf7bbb8`; the worktree is heavily modified. Preserve all existing changes. Deployable patches live in `local_deep_research/` and are mapped by `deployment/overlay-manifest.json`; edits in sibling `local-deep-research/` do not deploy. Production 5000/5002 and their source pool/model settings have not been changed by this hallucination experiment. Native fact consistency remains on and save-time citation QC remains off. Do not add automatic deletion, a hard publication gate, a body verification table, or topic-specific scientific regex rules. The former periodic monitor was cancelled by the user; do not recreate it.

### Active agents and ownership

| Agent | tmux target | Current responsibility |
| --- | --- | --- |
| Pane 0 | window 2 pane 0, stable pane `%22` | Owns application/runner/test edits and isolated candidate experiments. It is currently auditing first-stage passage filters after a source-first probe. |
| Pane 2 | window 2 pane 2, stable pane `%79` | Owns independent primary-source adjudication and review artifacts only. It is reviewing the full feedback and new candidate receipts. |

Both panes were confirmed alive in tmux at handoff. Capture their current screens before sending a new prompt; do not restart a live experiment or edit files owned by the other pane concurrently. Pane 2's [review directory](evaluation/pane2-independent-review-20261113/) contains its frozen rubric, issue mapping, and receipt hashes. The root coordination record is [here](docs/hallucination-coordination-20261113.md). This conversation's persistent root goal was cleared for handoff; the scientific objective remains unresolved. The new Codex should take ownership of that objective and only declare success after broad matched report assessment.

### Verified findings and failed attempts

1. **Original immune task inputs are authentic.** The unannotated [60-source production snapshot](evaluation/frontier-strategy-20261113/immune-evidence/production-original-sourcepack.json) is structurally identical to the source list in the original production synthesis trace (60/60; canonical SHA-256 `f66d8489f62d5169c1ec6095657b10dda26f32f2ecdb2dc4f4a7f3029405a172`). The same-trace [agent draft](evaluation/frontier-strategy-20261113/immune-evidence/production-agent-draft-0002.metadata.json) is 5,456 characters, SHA-256 `e91e62ecb4586b6c013f0c1264f8874a51f0235c28daace5c8a3c7203669f787`, and all 12 internal citation IDs belong to that source pack. Feedback annotations in `packet.json` are assessment data and must not enter generation.
2. **The first original-feedback pair is invalid.** Its starting PDF report used a different citation namespace, and all apparent model calls failed with 401 missing authentication; both outputs equalled that starting draft. Keep its [invalid-attempt receipt](evaluation/frontier-strategy-20261113/invalid-pair-diagnostic-20261113.json) as a failure record, never a quality result.
3. **The authenticated v2 pair ran, but its writer arms are confounded.** [Raw baseline and candidate receipts](evaluation/hallucination-next-phase-20261113/runs/matched-original-feedback-immune-v2-20261113T042334Z/) use the same authentic draft/source pack and real model calls, but they independently regenerated different pre-verification reports. Therefore baseline-to-candidate report differences cannot be credited to the verifier. The candidate's own pre-revision-to-final change is the only valid comparison of its post-write verifier. It extracted 74 claims: 7 complete, 1 partial, 66 uncovered; its reconciliation failed JSON parsing and produced zero rows, yet a revision changed 2 old claim texts (one only partially covered) and the text diff flagged 11 additions or rewrites. Pane 2 independently scored **0/7 original immune issues corrected** and found a new overgeneralization of source 9 beyond the study's cryopreserved bronchoalveolar-lavage setting. Read the [independent review](evaluation/pane2-independent-review-20261113/immune-candidate-v2-review.json). Do not deploy or claim hallucination improvement from this attempt.
4. **The dominant immune failure is before writing.** The original pack already contains nine decisive method spans in sources 5, 13, and 25, but **0/9 complete spans, including 80-character subspans, reached either actual writer prompt**. Source headers/titles were present; their decisive method text was omitted. The original Chinese query over English full text caused lexical no-match/structural sampling or weak single-letter matches. A manual English paraphrase alone recovered only 1/9. Source availability, valid citation IDs, and later native-check visibility are not proof that the writer read the methods. See the [exact writer visibility receipt](evaluation/frontier-strategy-20261113/writer-method-span-visibility-20261113.json) and [annotated assessment packet](evaluation/frontier-strategy-20261113/immune-evidence/packet.json).
5. **A small multilingual embedding did not solve it.** Under equal 2,000/6,000-character per-source budgets, manually supplied request-field lexical selection and isolated `multilingual-e5-small` each covered **2/9**, with different hits; E5 also selected a window from an unrelated negative. This is retrieval-only evidence on three feedback sources and synthetic controls, not a report gain or held-out generalization. See the [E5 comparison](evaluation/frontier-strategy-20261113/multilingual-span-recall-comparison-20261113.json). The E5 checkpoint was downloaded to a temporary local cache through the host proxy; no production dependency or model changed. An attempted global Chinese tokenizer change broke an existing Chinese retrieval test, was reverted, and that focused test passed again.
6. **The first source-first LLM probe was capped before ranking.** The [probe receipt](evaluation/frontier-strategy-20261113/source-first-field-probe-20261113.json) records 17/18 ranking calls completed and 1/9 method spans selected. The three source texts made 72, 148, and 213 original 1,800-character chunks; all nine annotated spans fit a chunk, but uniform sampling of only 16 chunks per source exposed just one span to the LLM. Its 1/9 is a first-stage candidate recall ceiling, not evidence that the LLM misranked eight unseen spans. All original chunks could expose 9/9, but would need an estimated 165 ranking calls at the current three-field/eight-chunk batching. The [all-chunk audit](evaluation/frontier-strategy-20261113/source-first-candidate-recall-20261113.json) makes this cost explicit. A new no-model-call [filter audit](evaluation/frontier-strategy-20261113/first-stage-filter-recall-20261113.json) is being revised by Pane 0; inspect the latest file and code before trusting its numbers. The nine source spans together fit the three sources' individual 6,000-character budgets, so aggregate context size is not the immediate obstacle. Separate-batch LLM scores are not automatically comparable.
7. **Other error families remain open.** In the diabetes trace, source 101 says *paraptosis* but the report says *necroptosis*; a real three-call source-only check found correct quotes but still reconciled the wrong relation as supported. The [v4 audit](evaluation/frontier-strategy-20261113/verifier-v4-supervisor-audit.md) explains why quote location does not prove entailment. Pane 2 substantiated eight bibliographic factual falsehoods separately from two scientific relation falsehoods; the current [identity audit](evaluation/frontier-strategy-20261113/identity-audit-20261113.json) only checks manually supplied report mentions. Automatic mention extraction/coreference and source-first relation/value comparison still need implementation and independent validation. Do not infer majority improvement from the immune case alone.

### Next actions

1. Finish and independently inspect Pane 0's current first-stage filter audit. Measure *oracle candidate recall before ranking* at several shortlist sizes and fixed text budgets, using all source chunks, lexical/multilingual dense scores and their union. Preserve source offsets and exact source identities. Do not use feedback spans to choose candidates. Check real held-out Chinese-to-English tasks and no-answer sources; synthetic controls and the current three sources are insufficient. Nonoverlapping chunks may split unseen method spans, so use structural boundaries with overlap. Do not pay for more LLM ranking until candidate recall and cost permit a meaningful test.
2. Derive neutral request fields from the original user question before seeing feedback or report claims. Apply source-first retrieval/reading to every relevant acquired source, then show in an actual writer prompt that key passages survive the **global** source budget. Keep source quotes and offsets; candidate relevance is not factual support. A fixed-source/draft report comparison must verify source-backed corrections and retain useful requested content. The runner has a new `--fixed-report` replay mode, but rerunning the unchanged post-write verifier is low value after its independently reviewed 0/7 result.
3. Extend beyond immune omissions: compare source-side and report-side subject, relation, value, qualifiers, scope and polarity independently for scientific claims; extract report bibliography assertions and resolve DOI/PMID identity before the existing identity audit. Keep outcomes advisory, preserve unknown/conflicts, and avoid automatic deletion or publication gates. Review across all six feedback tasks plus genuinely unseen questions. Pane 2 must score factual correction, citation support, requirement coverage, new errors and useful-content retention separately; do not claim the scientific objective is met until the full majority requirement is verified.

Focused evidence-flow regressions passed 45/45, the current semantic selector tests passed 13/13, and the Chinese retrieval regression passed 1/1 after rollback; these are module checks, not production quality proof. `git diff --check` passed at handoff. Additional research and experimental boundaries are in the [leader goal](docs/hallucination-leader-goal-20261113.md), [retrieval research](docs/hallucination-retrieval-followup-20261113.md), and Pane 2 review directory. Do not recreate the cancelled 30-minute timer or print credentials from local environment files.

## Repository layout

| Path | Purpose |
| --- | --- |
| `compose.yaml`, `deployment/` | Main deployment entry point, pinned base image, patch manifest, and SearXNG configuration |
| `local_deep_research/` | Patches installed into the image, the `research_verify` modules, and their tests |
| `local-deep-research/` | Vendored upstream source snapshot and its local development material |
| `ldr-monitor/` | Deployment diagnostics and historical operational notes; check machine paths before use |
| `docs/` | Source layout, deployment notes, current research flow, and development records |

API keys and other secrets are supplied through environment variables. Do not commit `.env`, deployment overlays, logs, or user data.

## Evidence workflow

The application collects stable source identities and evidence from the configured source pool, supplies abstracts and bounded full-text context to the writer, and records source ranges and private traces. Native fact-consistency checking is enabled for generated reports. The separate save-before-publication citation audit is currently disabled, and reports retain unresolved or unverified states when evidence is incomplete.

Source material and trace preservation improve inspectability; they do not guarantee that a model will interpret every study correctly. Full-text availability, search coverage, selection criteria, cross-topic accuracy, and semantic review remain limited. See the [current research flow](docs/current-research-flow-20261016.md), [source layout](docs/source-layout.md), and [research verification module](local_deep_research/research_verify/README.md) for implementation boundaries.

## Deployment

Requirements: Docker Engine and the Docker Compose plugin.

Run these commands from the repository root:

```bash
cp .env.example .env
# Edit .env with the model endpoint, model name, credentials, and a random SEARXNG_SECRET.
python -c 'import secrets; print(secrets.token_hex(32))'
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

Open <http://localhost:5000> and create the initial account. The default configuration listens only on the host loopback address. Remote access and migration details are documented in [Deployment](docs/deployment.md).

The root deployment starts from a pinned upstream runtime image and installs this repository's patches. Changes under `local-deep-research/` are not automatically installed into that image; the patch mapping and development boundary are described in [Source layout](docs/source-layout.md).

Useful commands:

```bash
docker compose logs --tail=100 local-deep-research
docker compose stop
```

Application data is stored in the `astro-dra_ldr_data` and `astro-dra_ldr_config` named volumes. User questions are also written as plain JSONL to `/data/logs/user_questions.log`; `LDR_ENABLE_FILE_LOGGING` does not control that separate question log.

## Testing

The project targets Python 3.12–3.14. From the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
PYTHONPATH=local_deep_research .venv/bin/python -m pytest -q local_deep_research/tests
```

These tests cover module behavior. They do not replace networked source checks, a complete research run, or semantic quality evaluation. Upstream tests use their own dependency environment; see [Source layout](docs/source-layout.md).

The upstream project is [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research), licensed under MIT; see [LICENSE](local-deep-research/LICENSE).
