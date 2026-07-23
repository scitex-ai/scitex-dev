---
description: |
  [TOPIC] Ecosystem cron — the worktree-gc job
  [DETAILS] `worktree-gc` is the second registered cleanup-style cron job (after `ci-watch`'s poll-style example). It walks configured home roots for repos with a `.claude/worktrees/` dir, filters `git worktree list --porcelain` output through `_is_managed_path` (only `.claude/worktrees/` survives; the operator's own `.worktrees/` is dropped), and removes managed worktrees older than `SCITEX_WORKTREE_GC_MAX_AGE_DAYS` via `git worktree remove` + `prune` (never force). The "only paths under `.claude/worktrees/` are ever touched" invariant and its `--dry-run`. Companion to [15_cron-management.md](15_cron-management.md).
tags: [scitex-general-package-cron-management]
---

# Ecosystem cron — the `worktree-gc` job

> Parent leaf: [`15_cron-management.md`](15_cron-management.md) — the four verbs, the marker convention, adding a job, and the `ci-watch` example live there.

## worktree-gc — the second registered cleanup-style job

`worktree-gc` is the second cleanup-style example (after `ci-watch`'s
poll-style example). It:

  1. Walks the user's home (configurable via
     `SCITEX_WORKTREE_GC_ROOTS`) finding every repo with a
     `.claude/worktrees/` directory.
  2. For each repo, runs `git worktree list --porcelain` and filters
     the output through `_is_managed_path` — only worktrees under
     `.claude/worktrees/` survive the filter; the operator's own
     `.worktrees/` is dropped here before any removal logic sees it.
  3. For each managed worktree, checks `mtime`. Older than
     `SCITEX_WORKTREE_GC_MAX_AGE_DAYS` (default 3) → candidate.
  4. `git worktree remove <path>` then `git worktree prune`. Git
     refuses dirty / locked / in-use worktrees → result records
     `skipped-refused`; nothing is force-removed.

The single highest-stakes invariant is "only paths under
`.claude/worktrees/` are ever touched." It is pinned by
`_is_managed_path`, by the per-worktree `_gc_one_worktree` boundary
check, by `os.walk`'s explicit skip of `.worktrees`, and by an
end-to-end test that hands the body a fake `git` runner returning both
a managed and a protected path and asserts `git worktree remove` is
called only for the managed one.

Verify the loop without touching anything:

```bash
scitex-dev cron exec worktree-gc --dry-run
```

This prints the would-be-removed worktrees and the reasoning per path
(fresh / stale / refused / errored) without invoking `git worktree
remove`.

Coordination: proj-scitex-agent-container owns the RELOCATION half —
stopping `.claude/worktrees/` from being created in the first place
(the canonical path will move to `.worktrees/` at the repo root).
Until that lands, this GC is the continuous cleanup loop.
