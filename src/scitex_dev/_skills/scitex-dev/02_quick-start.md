---
description: |
  [TOPIC] Quick start
  [DETAILS] Interpret doctor diagnostics and list registered packages; distinguish skipped checks, exposed environment values and optional version queries.
tags: [scitex-dev-quick-start]
---

# Quick start

After [installing](01_installation.md), use these commands to inspect the current
interpreter and ecosystem registry. A diagnostic report is not complete setup
or live-service acceptance.

## 1. `scitex-dev doctor`

Inspect Python and virtual-environment details, selected installed package
versions, editable source directories, relevant environment values, MCP tool
loading and agent-container screen sessions. The command also attempts PyPI
version queries, which depend on the network and the interpreter's pip. It does
not probe the archived orochi service.

```bash
scitex-dev doctor
scitex-dev doctor --json
```

JSON checks use `ok`, `fail` and `skip`; text uses `[OK]`, `[!!]` and `[--]`.
Any `fail` makes the command exit 1. Skipped checks are counted separately and
do not establish health, even when no check failed. An existing editable source
directory is checked without importing its package or repairing the install.

Review the output before sharing it: it includes paths and raw values of
`SCITEX_DIR`, `SCITEX_MCP_USE_*` and matching `SCITEX`/`DISABLE` variables.
It does not redact those values.

Owners: `_cli/_doctor.py` and `_cli/_doctor_editables.py`. Real PEP 610 fixture
controls live in `tests/scitex_dev/_cli/test__doctor_editables.py`; directory
existence is deliberately separate from import acceptance.

## 2. `scitex-dev ecosystem list`

The default output lists registered package names and GitHub repositories.
`--json` returns a `packages` array with `name` and `github_repo` fields; this
plain listing does not query package versions or report version drift.

```bash
scitex-dev ecosystem list
scitex-dev ecosystem list --json   # names and repositories
scitex-dev ecosystem list -p scitex-dev --versions --json
```

Use `--versions` explicitly for version details; that separate path calls
`list_versions` and may query remote sources. Source:
`_cli/ecosystem/_cmds/_list.py` and `_release/versions.py`. Do not interpret the
default registry listing as installed-package or live-host coverage.

From here you can:

- `scitex-dev ecosystem validate-versions --dry-run` — preview version drift fixes
- `scitex-dev ecosystem audit-skills` — audit `_skills/` directories across packages
- `scitex-dev ecosystem sync-local` — refresh editable installs

## Next steps

- Surface map: [04_cli-reference.md](04_cli-reference.md)
- Public Python API: [03_python-api.md](03_python-api.md)
- Per-workflow deep dives: see the **Workflows (10–19)** section in
  [SKILL.md](SKILL.md).
