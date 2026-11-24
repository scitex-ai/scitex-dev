---
description: |
  [TOPIC] Linter quick start
  [DETAILS] Validate a file or tree, read reported findings and skipped coverage,
  and use real Python checker functions without executing the checked source.
tags: [scitex-dev-linter-quick-start]
---

# Quick start

## Validate files

```bash
scitex-dev linter validate-files /owned/project/tool.py --json
scitex-dev linter validate-files /owned/project/src/ --json
```

Use the intended path. Normal completed validation exits 0 for no reported
findings, 1 for warning/info findings, and 2 when reported errors exist. A missing
path also exits 2. Finding no Python files exits 0 with a diagnostic, so zero
alone does not establish evaluated coverage.

For evaluated files, JSON contains file-path reports for reported findings and
`_meta` with skipped categories, `all_rules_ran` and applied file exemptions.
A clean file need not have its own report entry. Inspect those fields; an empty
finding set on the rules that ran is not complete coverage. Mandatory provider
and other processing failures remain failures.

## Inspect rules or a snippet

```python
from scitex_dev.linter import list_rules
from scitex_dev.linter.checker import lint_source

io_rules = list_rules(category="io")
issues = lint_source("VALUE = 1\n", filepath="tool.py")
```

The checker does not execute that source. Its filename affects configuration
and classification. `scitex_dev.linter._linter.check_source` and `check_files`
are not the interfaces to use; see [03_python-api.md](03_python-api.md).

Validation does not format files. For a formatting preview, use the separate
command with an explicit non-writing mode:

```bash
scitex-dev linter format-files /owned/project/tool.py --dry-run --diff
```

`--diff` alone also applies changes. See
[10_cli-reference.md](10_cli-reference.md) for preview modes and output gaps.
Hook installation and the consuming profile must be verified separately.

## Library directories

In source after 0.62.30, a project whose Python files are library modules can
declare its root in `pyproject.toml`:

```toml
[tool.scitex-dev.linter]
library_dirs = ["."]
```

The dot is relative to that configuration file, including when the CLI runs
from another directory. Absolute library directories match their resolved
descendants; sibling directories and symlinks targeting files outside the
configured root retain normal classification. Named entries such as `lib`
keep their existing directory-component matching behavior. The legacy
`[tool.scitex-linter]` table remains supported.

This classifies library modules for script-only checks; it does not exclude
files from linting. An unconfigured script still requires its `__main__`
guard. A directly constructed `LinterConfig(library_dirs=["."])` uses the
process's current directory instead of a configuration-file location.

The owning controls in `tests/scitex_dev/linter/test__source_helpers.py` use
real project files and CLI calls. Public package delivery is separate from
these source checks.

## Next steps

- [04_cli-reference.md](04_cli-reference.md) — CLI/configuration summary
- [06_quick-start.md](06_quick-start.md) — inspect Rule objects
- [07_rule-catalog.md](07_rule-catalog.md) — current catalog and coverage limits
- [10_cli-reference.md](10_cli-reference.md) — command behavior and output limits
- [11_mcp-tools.md](11_mcp-tools.md) — MCP contracts

Owning validation code: `_cmd_check.py`; existing controls include
`tests/scitex_dev/linter/test_cli.py` and `test__source_helpers.py`.
