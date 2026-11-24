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
`_meta` coverage as well as the exit status. Missing paths and empty selections
return before building that JSON object, so those paths do not provide `_meta`.

Coverage metadata reports the skip facts recorded by `_health.skipped_categories`:
`plugin_missing` for an empty IO/path tier when `scitex_io` is not importable,
and `requires_gate` for rule evaluations dropped because their declared
requirement is unavailable. `_meta.skipped_category_count` counts these records;
`skipped_categories` contains them, and `all_rules_ran` is true exactly when
that record list is empty. The quiet-notice setting does not suppress these
recorded facts. Missing optional coverage does not itself change the exit code.

An empty record list is not a complete coverage guarantee. For example, an
importable `scitex_io` with zero registered IO/path rules is not reported by the
current missing-plugin predicate. Before any plugin-load record, it also emits
no missing-plugin record. These unreported coverage gaps remain unresolved.
The metadata is process-global, including accumulated `requires_gate` counts;
it is not a per-file inventory, and it does not establish that every installed
provider or every rule evaluated. Human clean output is qualified with
`ON THE RULES THAT RAN` when the recorded list is nonempty.

Sources: `_health.py` and `_cmd_check.py::_do_check`. Owning controls:
`tests/scitex_dev/linter/test__health.py`, `test__cmd_check_skip_verdict.py` and
`test__health_corpus_provenance.py`. Some absent-provider verdict controls skip
when `scitex_io` is importable; retain those skips as incomplete coverage rather
than treating a passing installed-provider arm as proof of the absent arm.

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
scitex-dev linter mcp doctor --json
scitex-dev linter mcp start --dry-run --json
scitex-dev linter mcp install --json
scitex-dev skills list --package scitex-dev --json
scitex-dev skills get scitex-dev-linter SKILL --owner scitex-dev --json
```

Skill commands belong to Dev's root skills group, not a `linter skills` group.
Owner selection can include several namespaces of the same distribution.

MCP `list-tools` inspects the loaded server registry. Loading or introspection
failure exits 1 and reports a diagnostic on stderr. In JSON mode it also emits
`{"tools": [], "error": "..."}`; it never substitutes hard-coded names after a
failure. Success keeps `{"tools": ["..."]}` with sorted actual names. A registry
with no tools has an empty list, not a fallback catalog. Registry inspection
does not execute the tool bodies or prove a live server/client connection. `doctor` checks the FastMCP import,
registration-module import, CLI lookup and builtin rule count. A successful
registration import reports availability, not a registered or fixed tool count.
These prerequisites do not establish a live server/client round trip.
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

`doctor --json` emits `version`, `checks` and overall `ok`. Each check has `name`,
`ok` and `info`; overall `ok` is true only if all reported prerequisites pass.
Both output modes exit 0 when they pass and 1 when any check fails. For example,
a missing CLI on PATH is a failed check even when imports succeed. An importable
registration module can pass while the separate FastMCP dependency check fails.
The builtin rule count is not a provider-coverage report, and this command does
not load the linter server to count its registered tools.

Source: `_cmd_mcp.py`. Complete doctor JSON/text/exit controls, actual registered catalogs and real
settings-error controls, informational output, no-op flags, path quoting and
owned file-preservation controls live in
`tests/scitex_dev/linter/test__cmd_mcp.py`.
Actual tool contracts are in [11_mcp-tools.md](11_mcp-tools.md). Verify a configured
server, client and hook profile separately.

`_cmd_check._do_check` and its compatibility re-export `cli._do_check` also
reject `new_only=True` with the same `click.UsageError` message as the CLI,
before configuration or file analysis. A Python caller cannot enable the
forbidden gate mode through that re-export. Normal validation still reports
pre-existing errors at full severity. Historical `_new_only` classification
utilities remain for compatibility; they are not a supported validation mode.
Owning controls: `tests/scitex_dev/linter/test__cmd_check.py`,
`test__forbid_new_only.py` and `test__new_only.py`.
