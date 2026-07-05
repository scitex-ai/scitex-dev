---
description: |
  [TOPIC] CLI reference
  [DETAILS] `scitex-dev` subcommands grouped by category (Ecosystem, Development, Documentation, Interface, Shell) — entry-point summary, with pointers to per-command leaves.
tags: [scitex-dev-cli-reference]
---

# CLI reference

```
scitex-dev [OPTIONS] COMMAND [ARGS]...
```

## Global options

| Flag | Effect |
|---|---|
| `-V`, `--version` | Print version and exit |
| `-h`, `--help` | Show help |
| `--help-recursive` | Show help for every subcommand |
| `--json` | Emit structured JSON (propagated to subcommands that honour it) |

Config path resolution:
`./config.yaml → $SCITEX_DEV_CONFIG → ~/.scitex/dev/config.yaml → defaults`
(see [20_env-vars.md](20_env-vars.md)).

## Ecosystem

| Command | Description | Deep dive |
|---|---|---|
| `doctor` | Diagnose the health of the full SciTeX ecosystem | [02_quick-start.md](02_quick-start.md) |
| `ecosystem list` | Registry + installed/PyPI versions | [14_ecosystem.md](14_ecosystem.md) |
| `ecosystem fix-mismatches` | Repair version drift | [13_versions.md](13_versions.md) |
| `ecosystem sync-local` / `sync-host` | Editable / SSH sync | [14_ecosystem.md](14_ecosystem.md) |
| `ecosystem audit-*` | Skills / project / docs audits | [21_dynamic-audit.md](21_dynamic-audit.md) |

## Development

| Command | Description | Deep dive |
|---|---|---|
| `show-config` | Print the resolved `DevConfig` | [12_config.md](12_config.md) |
| `rename-symbols` | Bulk rename with cross-reference updates | [15_rename.md](15_rename.md) |
| `trace-env-vars` | Trace where env var(s) are defined/injected (static scan + strace) | — |

`trace-env-vars` is a diagnostic "silver bullet" for _where does this
env var come from?_ Two modes, both with word-boundary matching (`FOO`
never matches `FOO_BAR`) and secret-value redaction:

```bash
# Static scan (default): every assignment site across shell init
# files, direnv (.envrc walk-up), tmux global env, and current process.
scitex-dev trace-env-vars SCITEX_TODO_AGENT SCITEX_TODO_TASKS
scitex-dev trace-env-vars FOO --json      # structured envelope
scitex-dev trace-env-vars FOO -q          # one-line summary

# Dynamic trace: run a command under strace and report the FIRST exec
# stage whose child env carries the var (pinpoints multi-stage launches
# like shell -> tmux -> apptainer -> claude). Requires strace.
scitex-dev trace-env-vars SCITEX_TODO_AGENT --trace -- \
    sac agents start scitex-todo --yes
```

Two caveats to internalize:

- **Redaction is a conservative name heuristic, not a guarantee.**
  Values are redacted only when the variable name ends in one of
  `KEY`/`TOKEN`/`SECRET`/`PASSWORD`/`PASS`/`CREDENTIAL`/`AUTH`/`COOKIE`/`SESSION`.
  It catches `AWS_SECRET_ACCESS_KEY` and `GH_TOKEN` but MISSES
  `GITHUB_PAT`, `JSESSIONID`, `DATABASE_URL`-with-embedded-creds, etc.
  A non-redacted value means "not recognized as secret-shaped", not
  "confirmed safe" — don't over-trust it when sharing output.
- **`--trace` needs ptrace.** Inside a container without
  `CAP_SYS_PTRACE`, strace produces no data; the tool reports this
  DISTINCTLY as *trace inconclusive* (not a false "var never injected").

## Documentation

| Command | Description | Deep dive |
|---|---|---|
| `docs get / search / build` | View / search / rebuild aggregated docs | [16_docs-search.md](16_docs-search.md) |
| `skills list / get / export` | Manage skills across the ecosystem | spec under `_skills/general/03_interface/04_skills/` |

## Interface

| Command | Description |
|---|---|
| `mcp start / stop / status` | MCP (Model Context Protocol) server |
| `list-python-apis` | Tree of public Python callables |

## Shell

| Command | Description |
|---|---|
| `install-tab-completion` | Append a one-line eval to your shell's rc file |

## See also

- Full per-subcommand help: `scitex-dev --help-recursive`
- Test runner CLI: [17_test-runner.md](17_test-runner.md)
- Release pipeline: [18_full-update.md](18_full-update.md), [19_release-deploy.md](19_release-deploy.md)
