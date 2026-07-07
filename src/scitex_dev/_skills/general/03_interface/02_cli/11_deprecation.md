---
description: |
  [TOPIC] Interface Cli Deprecation
  [DETAILS] SciTeX CLI deprecation policy — three-phase ladder Warn (hidden alias forwards + once-per-shell stderr warning) → Error (exit 2 redirect) → Removed. Parameter-level deprecation warns once per shell session.
tags: [scitex-general-interface-cli-deprecation]
---

# §5. Deprecation — three-phase ladder (W → E → R)

Renamed commands walk a fixed three-phase ladder. Every phase names the
removal version, so callers always know the deadline.

| Phase | Name        | Behavior                                                                 | Exit |
|-------|-------------|---------------------------------------------------------------------------|------|
| **W** | Warn + forward | Hidden alias **invokes the new command** (`ctx.invoke`), stderr warning once per shell session | as new command |
| **E** | Error       | Hard error with a `Re-run with:` redirect — the alias no longer forwards | `2`  |
| **R** | Removed     | Alias deleted; standard "no such command" error                          | `2`  |

Each phase lasts at least one minor version (declare the schedule in the
warning message). Skipping straight to Phase E is allowed only for
commands that never shipped in a release.

## Phase W — warn + forward

- The old name stays as a **hidden** Click alias (`hidden=True` — absent
  from `--help` and tab completion) that forwards to the new command via
  `ctx.invoke`, passing all args/options through. Behavior is identical
  to the new command; only a warning is added.
- The warning goes to **stderr, once per shell session** — keyed by the
  parent shell's PID exactly like parameter-level deprecation (§5a
  below; marker file
  `${XDG_RUNTIME_DIR:-/tmp}/scitex-cli-dep-${USER}-${PPID}-<cmd>.flag`).
- The message **MUST state the removal version**:

```
'show-status' is deprecated — use 'status' (removed in v0.20)
```

- Shared helper:
  `scitex_dev/_ecosystem/click_compat.py::deprecated_alias()` (slice 2
  of the CLI-standardization plan — **not built yet**; until it ships,
  implement inline following this contract). The helper registers the
  hidden alias, wires the once-per-shell warning, and sets
  `cmd._deprecated_alias` metadata so the auditor can verify the alias
  statically instead of probing behaviorally.

## Phase E — hard error redirect

- The old form exits non-zero with a redirect (this was the *only*
  behavior under the previous doctrine — it is now the middle rung):

```
$ <cli> <old-name>
error: `<cli> <old-name>` was renamed to `<cli> <noun> <verb>`.
Re-run with: <cli> <noun> <verb>
```

- Exit code: `2`.
- Hard errors force stale scripts to be fixed in one iteration.
- No `-W ignore`-style silencer — the only way forward is to update the
  caller.

## Phase R — removed

- The alias is deleted. The old name gets Click's standard unknown-command
  error (exit `2`). Nothing in the tree remembers it.

## Why a ladder instead of hard-error-only

Hard-error-only (the old §5) breaks every caller — human and script —
on the same day the rename lands. Phase W keeps callers working while
the once-per-shell warning (not once-per-invocation — cron jobs and
loops would drown in it) surfaces the migration. Phase E then forces
the stragglers, and Phase R keeps the tree clean.

## §5a. Parameter-level deprecation

- For `--foo` → `--bar` where both still accept the same value:
  - Emit one stderr warning per shell session.
  - Stay silent for the rest of the session.
- Keyed by **the parent shell's PID** (i.e. `$PPID` from inside the CLI process) and command name. Using `$PPID` gives one warning per interactive shell, not per CLI invocation.
- Marker file: `${XDG_RUNTIME_DIR:-/tmp}/scitex-cli-dep-${USER}-${PPID}-<cmd>.flag`.
- Phase W command aliases reuse this exact marker mechanism.
