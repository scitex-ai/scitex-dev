---
description: |
  [TOPIC] When to merge `develop` → `main` (tag-push auto-sync)
  [DETAILS] The canonical rule that `main` = the latest tagged release, kept in
  sync by a single trigger — a tag push on `develop` auto fast-forwards `main`
  via `.github/workflows/sync-main.yml`. Includes the change-kind → action table
  (code/skills/docs all release via a tag; WIP stays on develop), the reference
  `sync-main.yml` workflow, and the manual fallback escape hatch when the
  workflow can't run. Companion to 01_version-control.md.
tags: [scitex-general-development-version-control]
---

# When to merge `develop` → `main`

**Canonical rule: `main` = the latest tagged release.** `main` is what
casual visitors see on GitHub; `develop` is where active work
integrates. We keep these in sync via a single trigger:

> **Tag push on `develop` automatically fast-forwards `main` to the tag.**

The mechanism is a small GitHub Action workflow at
`.github/workflows/sync-main.yml` that listens on `push: tags: ['v*']`
and runs `git merge --ff-only <tag>` on `main` (with a `--no-ff` merge
commit as fallback for non-linear histories). The bot pushes `main`
directly using `GITHUB_TOKEN` — no manual `checkout main` step needed.

### What this means in practice

| Change kind                           | Action to land it on `main`              |
|---------------------------------------|------------------------------------------|
| **Code/API/CLI/MCP change**           | Bump version, tag `vX.Y.Z`, push tag — workflow syncs `main` |
| **Skills / audit-rule rollout**       | Same: bump patch, tag `vX.Y.Z`, push tag |
| **README / docs polish (visible-on-GitHub change)** | Same — patch bump with `docs:` commit prefix is honest signaling |
| **In-flight refactor / WIP**          | Stay on `develop` — no tag yet           |

The patch-bump-for-docs idiom is intentional: any change that should be
visible on the GitHub landing page is a "release" of sorts (the README
is part of what users see when deciding whether to install). Tag it.

### Reference workflow

```yaml
# .github/workflows/sync-main.yml
name: Sync main with release tag
on:
  push:
    tags: ['v*']
jobs:
  ff-main:
    runs-on: ubuntu-latest
    permissions: { contents: write }
    steps:
      - uses: actions/checkout@v4
        with: { ref: main, fetch-depth: 0, token: '${{ secrets.GITHUB_TOKEN }}' }
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          TAG="${{ github.ref_name }}"
          git fetch origin --tags
          git merge --ff-only "$TAG" || git merge --no-ff "$TAG" -m "merge: sync main with $TAG"
          git push origin main
```

Reference exemplars: `scitex-ssh`, `scitex-dev`.

### Manual fallback (escape hatch)

If the workflow can't run (CI down, branch protection misconfigured,
etc.):

```bash
git -C ~/proj/PACKAGE checkout main
git -C ~/proj/PACKAGE pull origin main
git -C ~/proj/PACKAGE merge --ff-only vX.Y.Z       # or --no-ff if diverged
git -C ~/proj/PACKAGE push origin main
git -C ~/proj/PACKAGE checkout develop
```

If a pre-push hook blocks direct `git push origin main`, open a PR
`develop → main` instead and merge via `gh pr merge --merge`.
