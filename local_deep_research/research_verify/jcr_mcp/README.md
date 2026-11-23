# JCR catalog adapter

This package vendors the database reader from [jcr_mcp](https://github.com/yosh3289/jcr_mcp)
under its included MIT license. The reader uses a SQLite catalog built from
[ShowJCR](https://github.com/hitfyd/ShowJCR) tables.

Store the host-supplied catalog at `/data/journal_data/jcr.db` in the Compose
data volume so it survives image rebuilds. The app reads it without writing.
`LDR_JCR_CATALOG_PATH` can point to a different file mounted inside the
container. A catalog staged beside `jcr_database.py` is also accepted and
included in the build. Keep your SQLite catalog outside Git.

`research_verify.jcr_adapter` binds lookups to the cited journal and records the
metric year. Missing or ambiguous records stay unknown.
