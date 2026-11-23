---
description: |
  [TOPIC] Current linter rule catalog
  [DETAILS] Query the installed engine and provider metadata instead of keeping
  a duplicate ID/meaning/count table. Distinguish catalog presence from coverage.
tags: [scitex-dev-linter-rule-catalog]
---

# Rule catalog

The installed catalog is the source for current IDs, categories, severities,
messages and suggestions. Fixed rule-count and ID-to-meaning tables drift as
leaf providers own and evolve their rules.

```bash
scitex-dev linter list-rules --json
scitex-dev linter list-rules-all --json
scitex-dev linter list-rules-all --category io --json
scitex-dev linter list-rules-all --severity error --json
```

`list-rules` reads engine built-ins. `list-rules-all` and Python `list_rules()`
also load installed providers. JSON catalog entries contain `id`, `severity`,
`category`, `message` and `suggestion`. A filter such as `io` matches a category;
it does not mean every rule with a similar ID prefix. Use one category per
`list-rules-all` or Python query.

The Python `Rule` object additionally carries `requires` and `scope`.
Eligibility can depend on a runtime dependency, file classification or project
type. A catalog entry does not establish that its checker evaluated a particular
file. Inspect validation's skipped categories and failures; missing mandatory
providers must not be treated as a clean result.

The dispatcher loads declarations from `scitex_dev.linter.plugins`, with its
existing legacy-group support, ownership checks and collision refusals.
Rules stay with the package whose API they enforce. See the owning provider
source for domain semantics rather than inferring them from an ID prefix.
Sources: `_cmds/_rules.py`, `_plugin_loader.py`, `_rules/_base.py` and `_emit.py`.
Existing command controls live in
`tests/scitex_dev/linter/_cmds/test__rules.py`.
