---
description: |
  [TOPIC] Inspect linter rules
  [DETAILS] Use installed Rule metadata and canonical validation commands;
  catalog reads do not establish rule execution or complete coverage.
tags: [scitex-dev-linter-rule-walkthrough]
---

# Inspect the current rules

```python
from scitex_dev.linter import list_rules

rules = list_rules()
for rule in rules:
    print(rule.id, rule.severity, rule.category, rule.message)

io_rules = list_rules(category="io")
```

`Rule` has `id`, `severity`, `category`, `message`, `suggestion`, `requires` and
`scope` fields. It does not provide a `description` field. Category matching
uses exact category strings, not a rule-ID prefix.

```bash
scitex-dev linter list-rules-all --json
scitex-dev linter list-rules-all --category io --json
scitex-dev linter validate-files /owned/project/tool.py --json
```

Use `list-rules` for engine built-ins and `list-rules-all` for the catalog
including installed providers. Neither listing is a finding report; requirements
and scopes still affect which checks run on a file. Read validation's skipped
coverage and failures separately. Source: `linter/__init__.py`,
`_rules/_base.py`, `_cmds/_rules.py` and `_emit.py`.
