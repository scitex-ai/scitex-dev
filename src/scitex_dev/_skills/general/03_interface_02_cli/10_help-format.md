---
name: interface-cli-help-format
description: SciTeX CLI required `--help` output structure — description, synopsis, example, flags, exit codes.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §4. Help output format

`--help` always includes:

1. One-line description.
2. Usage synopsis: `Usage: <cli> <noun> <verb> [OPTIONS] ARG`.
3. **At least one concrete example.**
4. Flag list with descriptions.
5. Exit-code summary (if non-trivial).
