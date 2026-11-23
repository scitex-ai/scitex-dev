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
scitex-dev linter format-files /owned/project/tool.py --dry-run --diff --json
```

`--check` writes nothing and exits 1 if changes are needed; `--dry-run` writes
nothing and normally exits 0 even when changes are proposed. `--diff` prints a
diff but does not independently disable writing: without `--check` or
`--dry-run`, formatting applies changes. With both preview flags, `--check`
still determines the exit code.

`--json` emits one stdout object with `path`, the `check`, `dry_run` and `diff`
flags, `files`, `summary` and `error`. Each selected file has `file`, `changed`,
`written` and `diff` fields; clean files are included. The summary counts
selected files, proposed changes and actual writes separately. Requested Python
diffs are strings for changed files; other rows, including notebooks, use null.
Notebook formatting still applies to code cells; notebook diffs are unavailable.
A missing path emits an empty result with an error and exits 2; no selected
files emits an empty result with a null error and exits 0. Existing diagnostics
for these cases remain on stderr. File read, parse and write exceptions remain
visible failures rather than successful result objects; formatting is sequential
and does not promise rollback of earlier writes.

Sources: `_cmds/_format.py` and `_format_runner.py`. Behavioral evidence:
`tests/scitex_dev/linter/test__format_runner.py` exercises complete JSON objects,
exit codes, notebook metadata and preview/apply file effects through the CLI.

## MCP and skill discovery

```bash
scitex-dev linter mcp list-tools --json
scitex-dev linter mcp doctor
scitex-dev linter mcp start --dry-run --json
scitex-dev linter mcp install --json
scitex-dev skills list --package scitex-dev --json
scitex-dev skills get scitex-dev-linter SKILL --owner scitex-dev --json
```

Skill commands belong to Dev's root skills group, not a `linter skills` group.
Owner selection can include several namespaces of the same distribution.

MCP `list-tools` can fall back to known tool names if server loading fails; that
output alone does not prove tools are loaded. `doctor` checks dependency/tool
module imports, CLI lookup and a rule count, not a live server/client round trip.
`start --dry-run` starts no server; with `--json` it emits an intent object with
`action="start"`, the selected `transport` (`stdio` or `sse`) and `dry_run=true`.
This describes a preview and does not establish a running server. `install`
prints client configuration and never installs or changes it. Its `--json`
output is only the `mcpServers` configuration object, with the executable found
on PATH or the literal `scitex-dev` fallback and arguments
`["linter", "mcp", "start"]`. Quoted executable paths are JSON-escaped in both
output modes. The install `--yes` and `--dry-run` flags remain informational
no-ops. Native start still uses the selected MCP transport; the dry-run JSON
object is not a live-server status or protocol wrapper.

The accepted `doctor --json` option still produces text; that output gap remains.
Source: `_cmd_mcp.py`. Informational output, no-op flags, path quoting and owned
file-preservation controls live in `tests/scitex_dev/linter/test__cmd_mcp.py`.
Actual tool contracts are in [11_mcp-tools.md](11_mcp-tools.md). Verify a configured
server, client and hook profile separately.
