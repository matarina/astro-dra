# Metadata unknown states and original-field preservation — 2026-11-10

This undeployed candidate corrects metadata overclaims while preserving acquired sources. It is a component change with a frozen before/after comparison, not evidence of better scientific reports.

## Problem and implementation

Previously, preprint origin implied `not_peer_reviewed`. Source cards labeled absent adapter fields `not_reported`, which could suggest the paper omitted information even when the payload was only an abstract or metadata record. Cards and the native document builder also bound distinct fields by aliases: species→population, cohort→groups, n→sample size, instrument→platform, method/assay→technology, and publication type→study type/design. These inferences can silently change what a number or study attribute means.

The candidate leaves peer review unknown without an explicit typed boolean. A boolean remains a supplied assertion, accompanied by its original key/value and `not_independently_verified` provenance. It does not certify review quality or version applicability. [eLife's own process](https://elifesciences.org/about/peer-review) includes reviewed preprints. The Europe PMC authors describe review/version metadata in [their PLOS ONE paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0303005). Neither preprint status nor an empty review lookup establishes no peer review.

Cards now use `unknown`, reason `missing_metadata`, and a `missing_metadata` list for absent fields. Present values have `provided_metadata` status and their source key. The old negative `not_reported` list is removed from newly generated cards; historical traces are untouched. Do not use this card API to assert an independently reviewed paper omission.

Distinct scientific fields retain their original names in cards and native document metadata/material. Explicit canonical keys still work. Bibliographic `pubyear`/`publication_year` can supply year; a full publication date stays separately available rather than being mislabeled as a year. Publication types remain available as publication types, rather than inferred study design. Zero and false values survive reader serialization. This changes the card schema and may require downstream consumers to handle unknown/original keys; repository callers were searched and structural expectations updated.

Original-key metadata is data for the existing writer, not a new instruction block or a semantic verifier. Exact repetitions of already displayed dates/publication types are omitted; differing values stay visible. Unknown peer-review provenance remains in document/card metadata without a repeated prose header. Explicit boolean provenance is visible. Existing `GROUNDING_INSTRUCTIONS` bytes remain identical, native consistency stays enabled and save-time citation audits stay off. No source deletion, model request, topic filter, publication gate or automatic report edit is introduced.

Runtime files: `research_verify/source_identity.py`, `research_verify/evidence_cards.py`, `overlay/base_citation_handler.py`, `research_verify/generation.py`. Baseline/candidate snapshots also differ in the focused provenance test. The rollback is these four runtime files from the frozen baseline; deploy neither arm without the user's existing deployment constraints being satisfied.

## Freeze and real-source comparison

Before editing, preserve the current 159 application/deployment files, including prior candidates, under `/data1/maxw/ldr-evaluation/metadata-unknowns-20261110/baseline-code/`. This is a prospective baseline, not the original clean repository. Hash original Europe PMC responses for eight previously inspected development articles (six medicine/biology/bioinformatics, two forest-carbon controls), plus a newly fetched PPR279548 record. Freeze metadata contracts and protocol separately. See [freeze](../evaluation/metadata-unknowns-freeze-20261110.json).

The PPR279548 [official review endpoint](https://www.ebi.ac.uk/europepmc/webservices/rest/evaluations/PPR/PPR279548?format=json) returns review/evaluation links. Production preview metadata does not contain a peer-review boolean. Correct output from this limited payload is unknown; the candidate does not fetch reviews or automatically convert links into an authoritative review verdict. One larger initial search timed out. A separate PPR596760 exact-ID lookup returned zero, with an empty evaluation list; that missing record is excluded and the failed/empty responses retained, rather than labeled unreviewed.

Two disposable, network-disabled containers install baseline and candidate against the same application image. The actual installed Europe PMC preview method receives archived core API JSON through a request stub. Each arm then executes the actual native document builder and source formatter, without an LLM. No production engine configuration changes. The comparator verifies code/input hashes, ID/order equality, exact adapter-payload/document-text equality, complete supplied abstracts in both materials, and candidate values against their original source keys.

| Observed endpoint | Baseline | Final candidate |
|---|---:|---:|
| Returned records | 9 | 9 |
| Source payloads / native text unchanged across arms | 9/9 | 9/9 |
| Complete supplied abstracts present in both reader materials | 9/9 | 9/9 |
| Peer-review states | 8 unknown, 1 not_peer_reviewed | 9 unknown |
| Present card values | 52 reported_metadata | 52 provided_metadata |
| Default 12-column card slots | 52 present, 56 not_reported | 34 present, 74 unknown |
| Original-field slots added to candidate cards | — | 18 present |
| Candidate supplied card values located at original source keys | — | 52/52 |
| Total reader material characters | 23,134 | 23,124 |
| Model / live retrieval calls during replay | 0 / 0 | 0 / 0 |

The default-column change is mainly date and publication-type values moving to correctly named fields, not 18 missing facts. Total supplied-value count stays 52. None of these counts is scientific accuracy, source relevance or a hallucination rate. The metadata expectations are implementing-agent contracts, not independent expert gold.

Five separately frozen synthetic cases exercise distinct-field binding, explicit positive/negative review booleans, nonboolean review text and zero/false values. Candidate cards preserve every supplied diagnostic field under its original key; native material preserves species/cohort/n/instrument/method separately, with absent canonical scientific fields unknown. A direct formatting check also retains differing supplied dates while removing duplicate publication types. These are structural contracts only.

The first candidate increased reader material to 25,782 characters through repeated bibliographic data and unknown-provenance headers. Its entire source tree, results, manifest and comparison are preserved as `candidate-v1-*` / `comparison-v1.json`. A formatting-only follow-up removed exact duplicates; final installed replay preserved the same source/field contracts at 23,124 characters. This is development iteration on these inspected records, not held-out efficacy tuning or a measured token/latency gain. Sources with additional original metadata may still incur context overhead. Component replay took about 0.017 seconds per arm, excluding installation/import and all model work; this is not research latency.

## Validation and limits

Nineteen focused provenance checks, the feedback structural contract, final installed replay, source-preservation collection, compilation and diff checks pass. [Collector/results](../evaluation/metadata-unknowns-results-20261110.json) retain denominators, manifests, first-candidate hashes and synthetic diagnostics; [runner](../scripts/run_metadata_unknowns.py) and [collector script](../scripts/collect_metadata_unknowns.py) reproduce component processing. No raw bulk abstracts are added to the repository.

A broader five-file pytest run is **not green**: candidate 73 passed / five failed, preserved baseline 70 passed / the same five failed. See [failure triage](../evaluation/metadata-unknowns-test-triage-20261111.json). Several AST fixtures omit the installed collector mixin/current dependencies, one dereferences a missing artifact slot, and one fake finalize runner fails before checking recovery of earlier cited sources. These failures remain open; equal failure IDs do not establish that the intended behaviors work. The raw finalize skip/warning path merits separate investigation. No assertions were weakened or failures deselected. The first bootstrap attempt lacked pip; its error is retained. Five downloaded/hashed pure-Python test wheels were loaded only into disposable offline containers, without changing production dependencies.

Both temporary runs ended successfully and containers were removed. Production 5000/5002 were not restarted/deployed; production model/source pool and historical reports were not changed. Work stays on main, without a new branch or commit.

No independent claim/source annotations, fresh report generation, new paraphrase/adversarial synthesis comparison, retrieval recall, usefulness or cross-domain robustness endpoint is measured here. The earlier 16-pair report experiment contains older code, so its results do not validate these four module changes. Models may still infer scientific meaning incorrectly from original metadata; larger reader contexts may regress useful coverage. Identity/publication-state inference from apparent authoritative URLs remains a separate open audit item. Overall reliability improvement remains unproven.
