---
name: interface-cli-flags
description: SciTeX CLI universal flags — -h/--help, --help-recursive, --json, --dry-run, -V/--version, -v/--verbose, -q/--quiet, -y/--yes. No interactive prompts.
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §2. Universal flags

| Flag               | Purpose                                       | Required on                |
|--------------------|-----------------------------------------------|----------------------------|
| `-h`, `--help`     | Usage with at least one example               | Every command              |
| `--help-recursive` | Flatten help for all subcommands              | Top-level                  |
| `--json`           | Machine-readable JSON on stdout, no log noise | Every data-reading command |
| `--dry-run`        | Preview changes without side effects          | Every mutating command     |
| `--version`, `-V`  | Print `pkg/X.Y.Z`                             | Top-level                  |
| `--verbose`, `-v`  | Extra stderr logs (count style: `-v|-vv|-vvv`) | Optional                   |
| `--quiet`, `-q`    | Suppress non-error stderr                     | Optional                   |
| `--yes`, `-y`      | Bypass interactive confirm                    | Mutating commands          |

## Verbosity ladder

`--verbose` / `-v` is **count-style** — repeating it raises the level. Each level is **additive** (extends the previous level, never replaces). Required on the introspection commands ([03_required-introspection-commands.md](03_required-introspection-commands.md)); optional but recommended elsewhere.

| Level   | Meaning                                                                |
|---------|------------------------------------------------------------------------|
| (none)  | Default: minimal output (names, summary).                              |
| `-v`    | Adds signatures / one-line context.                                    |
| `-vv`   | Adds docstrings / multi-line detail.                                   |
| `-vvv`  | Adds source paths / JSON-schema / debug-level context.                 |

`--verbose` and `--quiet` are mutually exclusive — passing both → exit 2.

## No interactive prompts

- Commands must run unattended (CI, agent, cron).
- Missing input → fail fast with exit 2 + clear stderr.
- Never `input()`, `read`, or block on sudo.
- Mutating commands MAY show a confirmation prompt **only when stdin is a TTY**; otherwise auto-fail (use `--yes` to bypass even on a TTY).

## `--json` scope

- Required on every **data-reading** command (introspection, list, show, get, search, …).
- Recommended on every command that emits structured output the user might pipe.
- On non-data commands (lifecycle: `start`, `stop`, …) `--json` may emit `{"status": "ok"}` or be a no-op — the rule is: if the command exits, exit code carries the success signal; `--json` adds machine-readable detail when meaningful.
