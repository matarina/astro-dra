# PubMed relevance ranking and explicit date scope

The previous raw ESearch diagnostic found author-linked references below the default cutoff. This experiment sent identical questions through two installed native adapters. The candidate added only `sort=relevance` to ESearch. The pre-sort 170-file workspace snapshot, image, search caps, proxy and pacing were shared. This candidate is preserved as an isolated patch. [Previous retrieval diagnostic](fresh-evidence-retrieval-20261111.md) · [NCBI ESearch sort parameters](https://www.ncbi.nlm.nih.gov/sites/books/NBK25499/)

The published Best Match method uses BM25 followed by LambdaMART reranking of the first 500 results. Its authors report a held-out click-derived NDCG of 0.48 versus 0.15 for their previous TF–IDF method. The click data, document popularity features and 2018 operating conditions limit transfer to evidence coverage and current agent latency. That paper motivated a direct provider test with independent author references. [Fiorini et al., externally peer-reviewed, August 28, 2018](https://doi.org/10.1371/journal.pbio.2005343)

## Prospective ranking comparison

Before changing code, the panel froze six BioASQ bioinformatics families, six Evidence Inference clinical families and one social-media trial control. The normal questions and compact paraphrases yield 26 pairs. Eight further pairs test three literal date ranges, three adapter-level relative date limits and two unbounded questions asking for recent work. Each observation has a 25-preview cap. PubMed LLM optimization was disabled. Exact identity lookup resolved all 41 author-linked references. Date probes have a separate denominator from the normal references. Topics are new to the preceding rank diagnostic. The panel uses previously acquired public author data and manually selected question families.

| Endpoint | Provider default | Explicit relevance |
|---|---:|---:|
| Author-linked previews, all normal queries | 8/82 | 10/82 |
| Linked previews containing an author evidence span | 6/60 | 7/60 |
| Clinical author-linked previews | 4/12 | 4/12 |
| Bioinformatics author-linked previews | 3/68 | 5/68 |
| Social-media control author-linked previews | 1/2 | 1/2 |
| Directly relevant top previews, original queries | 1/13 | 1/13 |
| Mean seconds per normal query | 4.53 | 4.83 |

Both additional references came from bioinformatics paraphrases. There were zero linked-reference losses. The family-bootstrap recall difference was +2.44 percentage points with a descriptive 95% interval of 0 to +5.32. The implementer labeled 24 distinct top previews with arm hidden. Both arms had one direct, three background and nine unrelated top previews across the 13 original questions. All 34 pairs finished. The two arms submitted the same ESearch request sequence apart from sort in 33 pairs. One candidate response reported a partial provider failure and took a different fallback path. These results describe this cohort, with no automatic query planning, whole-list precision or report-level measurement.

The eight recency cases showed why the ranking patch stays isolated. All six relative-date arm observations sent the requested 365-day scope and returned no ESummary sort dates below the lower bound. The median age within the top 10 displayed results was 71 days with the default and 291 days with explicit relevance. One of three literal date-range cases lost its range on lexical fallback in both arms after zero results. The date-sort default happened to return no records with ESummary sort dates before 2025 in that case. Relevance returned 20. ESummary sort dates are a proxy for composition and can differ from other publication-date fields. The transmitted unscoped fallback independently proves the scope loss. In the two unbounded recent-wording cases, three of 12 dated top previews were from 2025 onward with relevance and four with the default.

The three normal direct top-preview judgments were identical between arms, with one direct, three background and nine unrelated results in each 13-family arm. This small blinded read does not show a relevance-quality gain. One candidate bioinformatics observation had a provider partial status. The normal linked-reference gain is therefore two identities in a convenience panel, with no report-generation or independent expert outcome.

## Date-scope correction

The workspace fix preserves explicitly tagged PubMed dates through query optimization and retries. A simple positive trailing date clause stays attached to the existing lexical fallback of its unfielded topic. Complex date expressions and queries with additional topic field tags stay intact. This keeps date scope as part of the actual query rather than post-filtering returned sources. Unscoped queries continue to use the existing optimizer and lexical retries. A scoped query can finish empty if its constrained retries find nothing. The current date fixture uses an unquoted endpoint form, and one candidate response still exposed a December 1 sort date under an upper bound of November 11. The input syntax is weaker than PubMed's documented quoted date-range form, so the correction is a regression safeguard rather than proof of date semantics. [PubMed date syntax](https://pubmed.ncbi.nlm.nih.gov/help/#dp) · [Adapter code](../local_deep_research/search_engine_pubmed.py)

The ranking patch and date-scope correction remain separate. The date fix passed its focused tests and the candidate installed suite. The complete suite remains partially red, with 107 baseline failures and 98 candidate failures in this isolated tree. No production deployment follows from either result.

The ranking archive at `/data1/maxw/ldr-evaluation/pubmed-relevance-holdout-20261111/` contains 355 files and has manifest SHA-256 `c890b861a6636e3a55ef4e55718ac23f7508e9c3317606b807869cb1656fd31b`. The date-scope archive at `/data1/maxw/ldr-evaluation/pubmed-date-scope-live-20261111/` contains 97 files and has manifest SHA-256 `c7e84e984ae8c233c48fcfda72fdc4b5154a4a58fa888c09817f125d7165ee47`.
