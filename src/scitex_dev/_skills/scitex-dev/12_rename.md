---
topic: rename
package: scitex-dev
description: >
  Bulk rename utility for files, file contents, directories, and
  symlinks with cross-reference updates. Enforces a guarded 5-step
  workflow (clean-git → dry-run → review → execute → test) so the
  classic refactoring footguns are systematically prevented. ALWAYS use
  this for any rename touching more than ~3 files; never fall back to
  per-file Edit calls or sed.
---

# Bulk Rename — `scitex-dev rename-symbols`

> Tool for "rename X to Y across the repo" / "consistent naming" /
> "refactor field names" / "update wire format". Updates every
> cross-reference (Python imports, TS imports, JSON keys, doc strings,
> file names, directory names, symlink targets) in one pass.

## Canonical 5-step workflow (the CLI guards each step)

| Step | What | How the tool enforces it |
|---|---|---|
| 1 | Clean git tree | `execute_rename` refuses if `git status` shows uncommitted changes (override: `--force`) |
| 2 | Dry-run preview | `execute_rename` refuses unless a recent `--dry-run` for the SAME (pattern, replacement, root, flags) tuple exists (override: `--force`) |
| 3 | Review the change list | The dry-run prints every match with a stable ID; abort and adjust if anything looks wrong |
| 4 | Real run | Same command without `--dry-run`; the lock from step 2 authorises it |
| 5 | Test the result | Post-execute hint reminds: `git diff`, run tests, then commit |

```bash
# Quick start — compound, unambiguous identifier:
scitex-dev rename-symbols pane_state orochi_pane_state --root . --dry-run
scitex-dev rename-symbols pane_state orochi_pane_state --root .
```

## Lock file location

Per-project (preferred) or per-user fallback:

| Where | When |
|---|---|
| `<project-root>/.scitex/dev/runtime/rename-locks/<key>.json` | `directory` is inside a git repo |
| `~/.scitex/dev/runtime/rename-locks/<key>.json` | not in a git repo |

Lock key = `sha1(pattern, replacement, abspath(root), regex, word_boundary)[:16]`.
TTL = 600 s (10 min). Reboots and TTL expiry both clear stale locks.

## Flags reference

| Flag | When to use |
|---|---|
| `--dry-run` | **Always.** No exceptions. The execute path requires this lock. |
| `--word-boundary` / `-w` | Renaming a word that's also a substring of other identifiers (`pane_state` inside `orochi_pane_state`). Treats `[A-Za-z0-9_]` as word chars. |
| `--regex` | Context-aware match (quoted-only, prefix anchor, variable-suffix family, path-segment). Replacement may use `\1 \2` backrefs. |
| `--skip-ids "f-003,d-001"` | Skip individual matches by ID from the dry-run output. Granularities: `c-NNN` (whole file), `c-NNN-L<n>` (one line), `f-NNN` (file rename), `d-NNN` (dir rename), `st-NNN` / `sn-NNN` (symlink target / name). |
| `--exclude <substr>` | Skip paths containing substring (repeatable). |
| `--force` | CI / scripted bypass for the uncommitted-changes check AND the dry-run gate. Use when the preview was audited out-of-band. |

## Recipes by pattern shape

| Pattern | Recommendation | Example |
|---|---|---|
| Compound identifier | Plain literal | `rename-symbols pane_state_evidence orochi_pane_state_evidence` |
| Generic word also used as path/class | `--word-boundary` | `rename-symbols machine orochi_machine -w` |
| Wire-format / dict-key only | `--regex` with quote anchors | `rename-symbols --regex "(['\"])model\\1" "\\1orochi_model\\1"` |
| Prefix anchor (start-of-name only) | `--regex` with `(?<![A-Za-z0-9_])` | `rename-symbols --regex "(?<![A-Za-z0-9_])v1_" "v2_"` |
| Variable-suffix family | `--regex` capture group | `rename-symbols --regex "xxx_(\\w+)" "yyy_\\1"` |
| Path-segment only | `--regex` lookarounds | `rename-symbols --regex "(?<=/)slurm(?=/)" "orochi_slurm"` |

## Skip-ids workflow

```bash
# Step 1 — dry-run, IDs printed beside each match:
scitex-dev rename-symbols project orochi_project --root . -w --dry-run
#   c-005-L42  bin/runner.sh:42      (keep)
#   f-003      examples/project/      (DON'T want)
#   d-001      hooks/project-switch/  (DON'T want)

# Step 2 — real run with offending IDs skipped:
scitex-dev rename-symbols project orochi_project --root . -w \
    --skip-ids "f-003,d-001"
```

## Recovery — every rename is reversible

```bash
# Whoops, produced double-prefix:
rename-symbols pane_state orochi_pane_state            # 1st pass
rename-symbols pane_state orochi_pane_state            # 2nd pass: orochi_orochi_pane_state

# Recovery (same flags, reverse direction):
rename-symbols orochi_orochi_pane_state orochi_pane_state -w --dry-run
rename-symbols orochi_orochi_pane_state orochi_pane_state -w
```

Pass `-w` on the recovery to avoid creating new collisions.

## Anti-patterns

- **Per-file Edit calls for a multi-file rename** — misses imports,
  JSON keys, TS property accesses; produces N noisy commits where the
  bulk renamer produces one clean one.
- **`sed -i` across a project** — breaks symlinks, doesn't know about
  git, no preview, no skip mechanism. Use this tool instead.
- **Globally renaming ultra-generic words** (`project`, `version`,
  `runtime`, `machine`) — even with `--word-boundary` they appear in
  template/example asset paths, hook subdirs, type annotations.
  Document via comments instead of a global rename, OR scope with
  `--regex` and quote anchors.
- **Skipping `--dry-run`** — the tool refuses to execute without one.
  This is by design; do the dry-run.

## Python API (advanced)

```python
from scitex_dev import preview_rename, execute_rename

# Preview (writes lock to <root>/.scitex/dev/runtime/rename-locks/):
preview = preview_rename(
    pattern="pane_state",
    replacement="orochi_pane_state",
    directory=".",
    word_boundary=True,
)

# Execute (requires matching recent preview, or force=True):
result = execute_rename(
    pattern="pane_state",
    replacement="orochi_pane_state",
    directory=".",
    word_boundary=True,
    skip_ids=["f-003", "d-001"],   # optional
    # force=True,  # bypass dry-run gate AND uncommitted check (CI only)
)

# RenameResult fields: contents, file_names, dir_names, symlink_targets,
# symlink_names, summary (dict with content_files / content_matches /
# files_renamed / dirs_renamed counts), error (None on success).
```

## MCP tool

Same workflow via the `dev_bulk_rename` MCP tool. Pass `confirm=False`
for dry-run, `confirm=True` for execute. The same dry-run gate applies.

## Execution order (for path integrity)

When the renamer changes both files and directories, it sequences
operations so paths never break mid-run:

1. File contents (safe — no path changes)
2. Symlink targets (point at future paths before the renames happen)
3. Symlink names
4. File names
5. Directory names (deepest first; children before parents)
