---
description: |
  [TOPIC] Github Actions — scitex-python monorepo-to-standalone transitional CI
  [DETAILS] scitex-python is transitioning from monorepo to standalone packages; use path-filtered reusable workflows where modules remain in-tree. Covers the module-specific caller shape (`test-stats.yml` triggering on `src/scitex/stats/**`, delegating to the reusable `_test-module.yml` which calls `./scripts/test-module.sh <module>`) and the per-module workflow/path-filter table. Companion to [07_github-actions.md](07_github-actions.md).
tags: [scitex-general-package-github-actions]
---

# scitex-python transitional CI pattern

> Parent leaf: [`07_github-actions.md`](07_github-actions.md).

## scitex-python Transitional Pattern

scitex-python is transitioning from monorepo to standalone packages; use path-filtered reusable workflows where modules remain in-tree.

```yaml
# test-stats.yml (module-specific caller)
on:
  push:
    paths: [src/scitex/stats/**, tests/scitex/stats/**]
jobs:
  test:
    uses: ./.github/workflows/_test-module.yml
    with:
      module: stats
```

The reusable `_test-module.yml` calls `./scripts/test-module.sh ${{ inputs.module }}`.

## Module-Specific Workflows Table

| Workflow file | Module | Path filter |
|---------------|--------|-------------|
| `test-io.yml` | io | `src/scitex/io/**` |
| `test-plt.yml` | plt | `src/scitex/plt/**` |
| `test-stats.yml` | stats | `src/scitex/stats/**` |
| ... | ... | ... |
