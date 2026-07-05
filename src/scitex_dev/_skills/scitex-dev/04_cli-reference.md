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
| `ecosystem check-versions` | Per-(host, package) develop-sha audit + sync (observe / dry-run / apply) | [13_versions.md](13_versions.md) |
| `ecosystem drift-report` | Unified per-package × per-layer VERSION matrix across all 8 drift layers; exit 1 on drift | [23_drift-report.md](23_drift-report.md) |
| `ecosystem fix-mismatches` | Repair version drift | [13_versions.md](13_versions.md) |
| `ecosystem sync-local` / `sync-host` | Editable / SSH sync | [14_ecosystem.md](14_ecosystem.md) |
| `ecosystem audit-*` | Skills / project / docs audits | [21_dynamic-audit.md](21_dynamic-audit.md) |
| `ecosystem audit-registry-layout` | PS-181 — `~/.scitex/<pkg>/` registry-layout conformance, scoped to the WHOLE `$SCITEX_DIR` tree (not a single repo) | — |

## Development

| Command | Description | Deep dive |
|---|---|---|
| `show-config` | Print the resolved `DevConfig` | [12_config.md](12_config.md) |
| `rename-symbols` | Bulk rename with cross-reference updates | [15_rename.md](15_rename.md) |
| `trace-env-vars` | Trace where env var(s) are defined/injected (static scan + strace) | — |
| `registry-normalize` | Fix PS-181 `~/.scitex/<pkg>/` registry-layout drift for ONE package (dry-run by default) | — |

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
- **`--trace` can take a while for multi-stage launches** (container
  boot, venv activation, etc.). On start it prints the live strace log
  path: always `$SCITEX_DIR/dev/runtime/trace-env-vars/` (default
  `~/.scitex/dev/runtime/trace-env-vars/`) — ONE fixed location
  regardless of the directory you run it from, so it's discoverable
  by both eye and script instead of scattering into whatever repo's
  `.scitex/dev/` happens to be nearby. Run `tail -f <path>` in another
  shell to watch execve stages arrive live. The log is kept after the
  run for later inspection; these accumulate over time and can be
  cleared manually. Once the trace finishes, every secret-shaped
  `NAME=VALUE` token in the SAVED file (envp and argv both) is redacted
  the same way as the structured report — same name-heuristic caveat
  above applies. The BRIEF live-tail window while the trace is still
  running shows the unredacted feed straight from strace, since
  redaction only rewrites the file after the command exits.

### `registry-normalize` — fix PS-181 registry-layout drift

Mechanically fixes drift in a SINGLE `~/.scitex/<pkg>/` state directory
against the canonical shape (`config.yaml` XOR `config/`; `runtime/`;
`logs/`; `archive/<UTC>/`; `bin/`/`scripts/`; a `<domain>/` dir per
authored content). Shares its detection logic with the PS-181 audit
rule (`scitex-dev ecosystem audit-registry-layout`) via
`scitex_dev.registry_normalize.scan` — one source of truth, so the two
surfaces can never disagree about what counts as drift.

```bash
scitex-dev registry-normalize scitex-todo             # dry-run (default)
scitex-dev registry-normalize scitex-todo --json       # structured plan
scitex-dev registry-normalize scitex-todo --yes        # actually move files
```

Hard safety rules (non-negotiable):

- **Dry-run by default.** Nothing is moved on disk unless you pass
  `--yes`/`-y`. Dry-run prints every planned move as `<from> -> <to>`.
- **Archive, never delete.** Every move has a destination; nothing is
  silently discarded. Loose `*.log` → `logs/`; loose
  `*.pid`/`*.sock`/`*.state`/`*_latest.json`/`ci-state.json` →
  `runtime/`; `_archive-<date>/` and `*.bak-<date>` → `archive/<date>/`;
  loose `*.py`/`*.sh` → `scripts/`.
- **Service-safe `*.pid` handling.** Before moving a `*.pid` file, the
  PID inside is checked for liveness (`os.kill(pid, 0)`). A live PID is
  SKIPPED (reported as `SKIPPED (live pid N)`), never moved out from
  under a running service.
- **`*.sock` files are ALWAYS skipped.** Liveness of a Unix socket is
  not cheaply determinable from the filesystem side, so every `*.sock`
  is reported as `SKIPPED (socket, assumed live — remove manually if
  stale)` regardless of `--yes`. Remove it by hand once you've
  confirmed the owning process is gone.
- **Exactly one `<pkg>` positional argument.** There is no "normalize
  everything" bulk mode — this tool acts on one package's state dir per
  invocation, on purpose.
- **Config-naming drift, stray `__pycache__/`, and venv-naming drift
  are reported by `audit-registry-layout` but NOT auto-moved here** —
  renaming a config file or a venv directory isn't a safe mechanical
  move (unlike relocating a log/pid/archive file to its canonical
  subdirectory), so those findings require manual attention.

### `ecosystem audit-registry-layout` — PS-181, whole-`$SCITEX_DIR` scope

Unlike every other `PS-1xx` rule (which audits a single repo checkout),
PS-181 inspects the user's ENTIRE `$SCITEX_DIR` tree (default
`~/.scitex`) — every installed package's local-state directory at once.
It is therefore wired as its own sibling command rather than folded
into `audit-project`/`audit-all` (which are inherently
per-distribution); see the docstring in
`_cli/audit/_project/_check_registry_layout.py` for the full rationale.

```bash
scitex-dev ecosystem audit-registry-layout                 # human output
scitex-dev ecosystem audit-registry-layout --json
scitex-dev ecosystem audit-registry-layout --severity info
```

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
