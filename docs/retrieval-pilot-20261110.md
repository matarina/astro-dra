# Native retrieval probe and explicit-scope candidate

This experiment is separate from the fixed-source synthesis pilot. It tests locating three known papers through six pre-frozen queries: a plain title and a concept query for each of medicine, biology and bioinformatics. Each native engine receives a preview budget of 25, with query optimization, LLM relevance filtering and report generation excluded. Sources and raw HTTP bodies are preserved privately at `/data1/maxw/ldr-evaluation/retrieval-pilot-20261110/`; [manifest](../evaluation/retrieval-pilot-freeze-20261110.json) and [results](../evaluation/retrieval-pilot-20261110.json) retain hashes and denominators.

## Observations

| Engine/configuration | Known targets located / queries | Returned previews | Other observations |
|---|---:|---:|---|
| PubMed baseline | 3/6 | 92 | 24 HTTP requests; mean 5.77 s |
| PubMed explicit-scope candidate | 3/6 | 92 | 18 HTTP requests; mean 4.20 s; all six returned PMID sets identical to baseline |
| Europe PMC unchanged baseline | 3/6 | 150 | Six HTTP requests; mean 2.94 s |
| Existing SearXNG route | 0/6 | 0 | All six JSON responses list upstream connection failures despite HTTP 200 |
| Isolated SearXNG, authenticated 2088 route, Bing | 0/6 | 10 total | Ten results from one query point to Surfshark/VPN pages; other queries empty. Connectivity is not relevance. |
| Isolated SearXNG, same proxy, DuckDuckGo/Brave/Google | 0/6 | 0 | DuckDuckGo CAPTCHA; Brave rate limit/suspension; Google parsing error on one query. All six carry upstream failure metadata. |

A first alternative-backend container failed to bind port 18890. Requests to that address were confounded and are **excluded**, with the failure retained in the manifest. The replacement used a Docker-assigned port and `/config` verification of the enabled engines before querying. No production service was changed.

## Candidate change

The baseline PubMed `_adaptive_search` estimates topic volume, classifies historical intent, then adds a 1/3/5/10-year filter even when the caller supplied no date restriction. The captured DAPA-CKD and scVI queries show appended five-year filters that exclude their original publication years. Broad queries can still return recent matches, so the old policy never necessarily falls back to all years. This can silently narrow scope.

The candidate sends the supplied query once, without volume- or intent-derived dates. Explicit query-date syntax and operator `days_limit` are retained. This removes an unjustified semantic assumption; it does not automatically solve ranking, query interpretation or fixed-budget coverage. No extra model prompt, topic rule, deletion or publication gate is added.

The candidate was developed after baseline observations, using the already frozen queries. It is a development comparison, not an untouched held-out result. On these six queries it removes six count requests while preserving all returned PMID sets. That demonstrates request reduction in this probe; sequential live timing does not establish a causal latency improvement. The two unchanged misses for DAPA-CKD and the scVI title query show the remaining ranking/query-budget limitation.

## Evaluation limits and next steps

Known-item locating is not overall literature recall. Other returned records are not independently relevance-labelled, so precision and total relevant-literature recall remain unmeasured. Cross-engine result counts cannot be compared as relevance scores. PubMed and Europe PMC source pools are biomedical indexes; the small query set cannot establish cross-domain robustness or downstream usefulness. Native LLM relevance filtering and writer behavior require separate matched evaluation.

Free SearXNG backends were tested only in isolated instances. [SearXNG's DuckDuckGo implementation](https://docs.searxng.org/_modules/searx/engines/duckduckgo.html) documents no-key operation and bot-blocking uncertainty. [Brave documentation](https://docs.searxng.org/dev/engines/online/brave.html) distinguishes the web scraper from its keyed API. The observed CAPTCHA/rate limits are an external availability constraint; no bypass was attempted and no production backend switch was made.

Three scope-policy tests verify unchanged queries, explicit-date empty responses and absence of volume/intent classifier calls. Three collection tests verify HTTP200/upstream-error handling, payload hashes and transport failures. These are regression checks, not a measured reduction of hallucinations. Retrieval and report effectiveness remain unproven beyond the stated probe.
