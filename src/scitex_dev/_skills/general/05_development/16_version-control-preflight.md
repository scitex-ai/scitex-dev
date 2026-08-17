---
description: |
  [TOPIC] Version-Control Preflight — respect the working tree
  [DETAILS] The state checks to run against each target package before any
  `ecosystem pull` / `install` / `checkout` or release-cut step: uncommitted
  local changes (commit / stash / discard-gitignore), not-on-`develop` (feature
  branch reconciliation, merged-branch cleanup, detached HEAD), and upstream
  tracking (phantom `↑N`/`↓N` from a misconfigured upstream). Companion to
  01_version-control.md.
tags: [scitex-general-development-version-control]
---

# Preflight: respect the working tree

Before any `ecosystem pull` / `install` / `checkout` (or release-cut
step below), check **each target package's** state. Two conditions
can swallow work or hide regressions:

### 1. Uncommitted local changes

```bash
git -C ~/proj/<pkg> status --porcelain
```

If non-empty, decide per file:

- **Commit** — real work (e.g. a doc revision, a source fix). Stage
  the intentional files only; do not `git add -A` blindly.
- **Stash** — transient experiment you'll come back to. Use a named
  stash (`git stash push -m "<reason>" -- <paths>`).
- **Discard / gitignore** — runtime artefacts (e.g.
  `.scitex/<pkg-short>/runtime/*.sqlite`, build caches). These
  belong in `.gitignore`, not in a stash; if you see them dirty
  repeatedly, fix the ignore pattern.

`ecosystem pull` will fail noisily on dirty trees — that's the
desired behaviour. Do not silence it with `--force` flags.

### 2. Not on `develop`

```bash
git -C ~/proj/<pkg> rev-parse --abbrev-ref HEAD
```

If the current branch isn't `develop`:

- **Feature branch with unmerged work** — finish or abandon
  intentionally; do **not** `ecosystem checkout develop` until the
  branch is reconciled. A pending feature branch with `↑N` commits
  ahead of develop is real work in flight.
- **Feature branch already merged into develop** — delete it:
  ```bash
  git -C ~/proj/<pkg> branch -d <branch>           # local
  git -C ~/proj/<pkg> push origin --delete <branch> # remote
  ```
  Then `git checkout develop` and proceed.
- **Detached HEAD / stale tag checkout** — `git checkout develop`
  first; investigate why HEAD wasn't at a branch tip.

### 3. Upstream tracking

```bash
git -C ~/proj/<pkg> branch -vv | head -5
```

Verify each tracked branch's upstream points at `origin/<branch>`,
not a stale fork or local mirror. A misconfigured upstream
(`scitex/develop` localhost-Gitea instead of `origin/develop`)
produces phantom `↑N` / `↓N` counts and breaks `gui`.
Fix with:

```bash
git -C ~/proj/<pkg> branch --set-upstream-to=origin/develop develop
```

After preflight, the rest of this skill (and the `/update-scitex`
command) assumes every target is on `develop`, clean, and tracking
the right remote.
