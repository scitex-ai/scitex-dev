---
description: |
  [TOPIC] Linter command behavior
  [DETAILS] Canonical validation/catalog/formatting commands, normal exit
  behavior and explicitly unresolved output/health-coverage limits.
tags: [scitex-dev-linter-command-behavior]
---

# Command behavior

## Validate and inspect

```bash
scitex-dev linter validate-files /owned/project/tool.py --json
scitex-dev linter validate-files /owned/project/src/ --category io --json
scitex-dev linter list-rules --json
scitex-dev linter list-rules-all --category stats --json
```

For completed validation, exit 0 means no reported findings, 1 means reported
warning/info findings, and 2 means reported errors. Missing paths exit 2;
no collected files can exit 0 without evaluating a file. Read the result's
`_meta` coverage as well as the exit status.

`--severity` is a minimum reporting filter, defaulting to `info`; catalog
`--severity` filters exact metadata values. The validation filter remains
separate from the loaded `LinterConfig.severity` field. That consumption gap is
unresolved; configuration details are in [04_cli-reference.md](04_cli-reference.md).
`--new-only` is forbidden and returns a usage error; it is not a supported way
to accept existing findings. `check` and `check-files` are deprecated
compatibility aliases; use `validate-files` in new commands.

## Formatting is separate

```bash
scitex-dev linter format-files /owned/project/tool.py --check
scitex-dev linter format-files /owned/project/tool.py --dry-run --diff
```

`--check` writes nothing and exits 1 if changes are needed; `--dry-run` writes
nothing and normally exits 0 even when changes are proposed. `--diff` prints a
diff but does not independently disable writing: without `--check` or
`--dry-run`, formatting applies changes. The accepted `--json` option currently
still produces line-oriented output; structured formatting output remains an
implementation gap. Sources: `_cmds/_format.py` and `_format_runner.py`.

## MCP and skill discovery

```bash
scitex-dev linter mcp list-tools --json
scitex-dev linter mcp doctor
scitex-dev linter mcp start --dry-run
scitex-dev skills list --package scitex-dev --json
scitex-dev skills get scitex-dev-linter SKILL --owner scitex-dev --json
```

Skill commands belong to Dev's root skills group, not a `linter skills` group.
Owner selection can include several namespaces of the same distribution.

MCP `list-tools` can fall back to known tool names if server loading fails; that
output alone does not prove tools are loaded. `doctor` checks dependency/tool
module imports, CLI lookup and a rule count, not a live server/client round trip.
`start --dry-run` starts no server. The accepted `--json` options on `doctor`
and `start --dry-run` currently remain text-output gaps. Source: `_cmd_mcp.py`;
actual tool contracts are in [11_mcp-tools.md](11_mcp-tools.md). Verify a configured
server, client and hook profile separately.
