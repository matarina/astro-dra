# Native fact checker review units

The held-out report evaluation found three contradicted assertions that the native checker marked supported even though it had access to the relevant sources. The current checker combines adjacent prose into paragraph units. This experiment isolates whether the boundaries of those units affect the checker's ability to identify individual assertions that lack support. [Prior trace diagnosis](reserved-trace-diagnosis-20261111.md)

## Paired design

The panel contains 24 short drafts from 12 families. Eight biomedical families use 24 distinct SciFact claims and abstract records, with one support, one contradiction and one insufficient-evidence example per family. Both the claims and source records are disjoint from the previous 90-case checker calibration. Each family appears once with an ordinary heading and once with a certainty-seeking heading and reversed sentence order. That second variant tests the combined perturbation. The eight insufficient-evidence references received a reading-scope check before comparing arms. The primary labels follow the benchmark. [SciFact paper, EMNLP 2020](https://aclanthology.org/2020.emnlp-main.609/) · [Author data release](https://github.com/allenai/scifact)

Four controls from the VitaminC real development split cover film, music and political history. For each family, both drafts contain the same focal assertion and the same two comparison assertions. One supplied passage supports the focal assertion and the other refutes it. Each focal pair shares the `wiki_revision_id` recorded by the author release. Its two author record IDs identify distinct evidence passages. The artifact retains both IDs without inferring separate upstream revision identifiers. [VitaminC paper, NAACL 2021](https://aclanthology.org/2021.naacl-main.52/) · [Author data release and license](https://github.com/TalSchuster/VitaminC)

Both arms use the same frozen runtime, model, native prompt instructions, draft bytes, source passages and citation numbers. The current paragraph extractor supplies 24 units across 24 drafts. The existing sentence extractor supplies 72 units, all matching their frozen assertion spans and citation numbers. One native checker call per arm receives all three complete supplied sources. Temperature is 0 with a maximum of 30,000 tokens. The panel uses constructed three-assertion paragraphs with independent author labels. The source material is limited to supplied abstracts and Wikipedia passages, and prior model exposure to these public data is unknown.

An explicit sentence unit ID can locate an overall verdict. A paragraph verdict can locate an individual assertion only if a returned atomic claim value matches a unique sentence in that unit. The atom-only sensitivity analysis applies that same match rule to both arms. A matched atom may cover just one attribute, so the score measures returned decisions and their localization. For a localized contradiction atom, the artifact separately records whether the quoted text occurs in the assertion's designated source. Entailment still requires reading the claim against the passage. Insufficient evidence and contradiction have separate labels. Unlocalized atoms, missing units and unparseable responses are retained.

The private archive at `/data1/maxw/ldr-evaluation/native-review-boundaries-20261111/` contains the input and scoring protocols, original dataset archive, gold labels, queue, prompts, responses and trace receipts. The input manifest SHA-256 is `bdd0e5eb9047d9104a52febce8e8cfb0f88e11e270ae201be7abdeda0b576af5`. The frozen queue SHA-256 is `169288be36fb0fbc07316b3586f8c9995b35c807fecf45f08c72812a6d1e0685`.

## Results

| Outcome | Paragraph | Sentence |
|---|---:|---:|
| Non-supported assertions flagged at the correct location | 31/44 | 31/44 |
| Contradictions called contradictions | 22/28 | 19/28 |
| Biomedical contradictions called contradictions | 13/16 | 10/16 |
| Insufficient evidence called insufficient evidence | 4/16 | 6/16 |
| Insufficient evidence called contradiction | 5/16 | 6/16 |
| False flags on supported assertions | 4/28 | 6/28 |
| Correct label among all assertion instances | 44/72 | 45/72 |
| Correct label among biomedical instances | 27/48 | 25/48 |
| Correct label among nonmedical instances | 17/24 | 20/24 |
| Assertions with no localized decision | 7/72 | 6/72 |
| Parseable checker responses | 24/24 | 24/24 |
| Total reported tokens | 62,849 | 62,890 |
| Mean / median checker seconds | 6.24 / 5.94 | 5.83 / 6.02 |

Using only matched atom values on both arms produces the same counts. The paired family mean difference in non-support localization was 0 percentage points, with a descriptive 95% family-bootstrap interval of −14.6 to +14.6 points. False flags rose by a family mean of 6.9 points, with an interval of 0 to +16.7. Biomedical localization was 22/32 in both arms. It went from 9/16 to 10/16 under the ordinary heading and from 13/16 to 12/16 under the combined heading-and-order perturbation. Each arm correctly labeled both focal passages for two of the four nonmedical pairs, with the successful families differing. These intervals and subgroup counts describe this small panel.

The paragraph arm returned a decision under all 24 unit IDs and repeated the same unit ID in 23 of 24 calls. The sentence arm returned 66 of 72 unit IDs, with omissions in three calls and zero duplicate IDs. All calls used the same source bytes. The checker returned 37 exact designated-source quotes for 41 localized paragraph contradiction atoms and 33 for 38 sentence contradiction atoms. The sentence arm used 1,546 more reported input tokens and 1,505 fewer output tokens. Each draft fit in a single review call in both arms, so the latency measures cannot estimate how the eight-unit batch limit would affect long reports.

The source passages show errors that changing unit boundaries alone leaves unresolved. On one biomedical case, the sentence arm marked reduced T-cell receptor diversity as supported by a passage reporting diversity comparable to healthy individuals. On a nonmedical control, it marked a value of $50.7 million as contradicting a claim of less than $50.8 million. Some benchmark labels also require care. The nonmedical history passage labeled `REFUTES` describes the group overthrowing a dynasty but omits the king's name. The SciFact fitness passage labeled `CONTRADICT` compares cardiovascular risk factors by fitness level and omits the asserted mortality outcome. The primary counts preserve the author labels and therefore measure agreement with the benchmark, including these boundary cases.

Keep paragraph review as the runtime default. The next candidate test can isolate citation scope while retaining neighboring sentences, with independent labels on full biomedical and bioinformatics drafts, including paragraph-end citations, shared sources and table context. Source recall, report usefulness and long-report latency need their own matched measurements. The 48 calls here support a component comparison. The effect on end-to-end report grounding remains unproven.

The sealed archive manifest covers 162 files and has SHA-256 `c0d56fd769d8691ceb70000f95aa56640d0f8aa03595be3e8f4f8e77926aa10d`. The detailed score SHA-256 is `e56dd934c31ffbefa679a1098653640fc669f1bba705ff51994f42780d13e7e5`.
