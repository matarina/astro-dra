# Evidence-grounding checkpoint

This checkpoint is intentionally scoped to reusable APIs in the owned
`local_deep_research/research_verify/` overlay. It adds an evidence-grounding
receipt, explicit research-scope metadata, held-out manifest validation, and a
fail-closed manual-review acceptance helper. The modules do not edit report
text, publish gates, or production defaults.

The held-out acceptance path now rejects empty, missing, duplicate, mismatched,
or unbound review rows when frozen claim or case IDs are supplied. Repeated case
IDs are valid across distinct claim IDs. A zero-assertion case is valid only
when both arms provide a complete case receipt with an explicit reason. The
held-out dataset, private gold, arm key, reviewer packet, run outputs, source
bytes, and provider traces are excluded from this branch.

Validation performed on the clean worktree included nine focused grounding and
acceptance tests, Python import/compile checks, and `git diff --check`. The
checkpoint does not claim hallucination reduction, production integration, or
human acceptance. The untouched `origin/main` baseline also has an existing
test-collection failure because `publication.py` imports `paper_identity` from
`evidence.py`, where that symbol is absent. That unrelated dependency mismatch
is outside this checkpoint and was not broad-copied into it.
