# JCR catalog adapter

This package vendors the database reader from [jcr_mcp](https://github.com/yosh3289/jcr_mcp)
under its included MIT license. The reader uses a SQLite catalog built from
[ShowJCR](https://github.com/hitfyd/ShowJCR) tables. Provide a local catalog named
`jcr.db` beside `jcr_database.py` to enable journal metrics. Without a catalog,
DRA cannot supply a verified metric.

`research_verify.jcr_adapter` binds lookups to the cited journal and records the
metric year. Missing or ambiguous records stay unknown.
