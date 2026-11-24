---
description: |
  [TOPIC] Env Vars
  [DETAILS] Settings read by the linter configuration loader; distinguish rule-ID lists, filename/path classification, command-specific output filters and notice verbosity.
tags: [scitex-dev-linter-env-vars]
---

# scitex-dev linter — Environment Variables

Canonical prefix: **`SCITEX_DEV_LINTER_`**. The engine accepts the legacy
`SCITEX_LINTER_` prefix for the soft-migration window (one release) and
emits a `DeprecationWarning` naming the canonical replacement.

`config._load_env` reads the settings below over the selected pyproject table.
CSV settings replace the corresponding list; they are not Boolean switches.
Defaults come from `LinterConfig` when no environment or TOML value supplies them.

| Variable | Loader result | Default |
|---|---|---|
| `SCITEX_DEV_LINTER_DISABLE` | CSV rule IDs in `config.disable`; not a global off switch | `[]` |
| `SCITEX_DEV_LINTER_ENABLE` | CSV gate entries in `config.enable`, including `FM` for the figure category | `[]` |
| `SCITEX_DEV_LINTER_SEVERITY` | `config.severity`; `validate-files` uses its separate `--severity` reporting filter | `info` |
| `SCITEX_DEV_LINTER_EXCLUDE_DIRS` | CSV excluded-directory names used during file collection | `__pycache__,.git,node_modules,.tox,venv,.venv` |
| `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` | CSV library-directory entries for script-only classification | `src,tests,apps,config,docs` |
| `SCITEX_DEV_LINTER_LIBRARY_PATTERNS` | CSV filename glob patterns; see `LinterConfig.library_patterns` | built-in filename patterns |
| `SCITEX_DEV_LINTER_SCRIPT_DIRS` | CSV utility-script directory entries, also exempt from script-only classification | `scripts` |
| `SCITEX_DEV_LINTER_REQUIRED_INJECTED` | CSV session injection names | `CONFIG,plt,COLORS,rngg,logger` |

`SCITEX_DEV_LINTER_DISABLE=true` loads the literal entry `"true"`; it does not
turn linting off. Rule-ID settings do not bypass mandatory logging-provider
coverage. `SCITEX_DEV_LINTER_QUIET` separately suppresses eligible notices in
`_health.py`; it is not a coverage or checker-failure waiver.

`validate-files --severity` defaults to `info`, independently of the loaded
severity field. Wiring that configuration field to this CLI filter remains an
unresolved consumption gap. Likewise, the loader does not consume a
`SCITEX_DEV_LINTER_CONFIG` YAML path. See [configuration limits](04_cli-reference.md#configuration-sources-and-limits).

## EXCLUDE_DIRS vs NON_SCRIPT_DIRS

Two related concepts that previously shared an ambiguous name:

| | `EXCLUDE_DIRS` | `NON_SCRIPT_DIRS` |
|---|---|---|
| Lint runs on files? | **No** — skipped entirely | **Yes** — file is linted |
| Which rules fire? | None | All except script-only (S001/S002/S003/S004/S005) |
| Typical entries | `__pycache__`, `.git`, `node_modules`, `.venv` | `src/`, `tests/`, `apps/`, `config/` |

## Deprecation aliases

The following legacy names are still read but emit a `DeprecationWarning`:

| Legacy | Canonical |
|---|---|
| `SCITEX_LINTER_*` (any suffix) | `SCITEX_DEV_LINTER_*` |
| `SCITEX_DEV_LINTER_LIBRARY_DIRS` | `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` |
| `SCITEX_LINTER_LIBRARY_DIRS` | `SCITEX_DEV_LINTER_NON_SCRIPT_DIRS` |

## Coverage controls

List settings and quiet notices have the scopes above; there is no global
Boolean disable implemented by this loader. Source: `config.py`,
`_source_helpers.py`, `_collect.py`, `_emit.py` and `_health.py`. Research project
requirements and mandatory provider checks retain their existing behavior.

## Audit

```bash
grep -rhoE 'SCITEX_(DEV_)?LINTER_[A-Z0-9_]+' $HOME/proj/scitex-dev/src/scitex_dev/linter/ | sort -u
```
