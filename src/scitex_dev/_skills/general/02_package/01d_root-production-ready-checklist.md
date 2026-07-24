---
description: |
  [TOPIC] Package Root — production-ready invariant, anti-patterns, pre-release checklist
  [DETAILS] The root-hygiene appendix for a SciTeX package: the "production-ready always" invariant (main branch publishable today — half-finished work on feature branches, obsolete files under `.old/`, examples run clean, tests pass, README current), the root anti-patterns (top-level junk flagged by PS-103, naked `src/`, `tests/` not mirroring `src/`, examples with no `_out/`, uncategorized `.dev/`, ever-growing `.old/`, umbrella `scitex` imported from `src/`), and the pre-release / major-review checklist. Companion to [01_project-structure-root.md](01_project-structure-root.md).
tags: [scitex-general-package-project-structure-root]
---

# Root — production-ready invariant, anti-patterns, checklist

> Parent leaf: [`./root`](01_project-structure-root.md).

## Production-ready always

The main branch must be publishable **today**, regardless of in-flight work:

- Half-finished features are on `feature/<verb>-<object>` branches, never on `main`.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Top-level junk** (any `*.png` debug screenshot, `tmp_test.py`, `quick_check.py`, `debug.log`, `untitled.ipynb`, `current-snapshot.yml`, …) — flagged by **PS-103** strict whitelist. Move to `./docs/assets/` (if referenced from docs), `./.dev/<category>/` (if scratch), or delete. Bulk cleanup: `scitex-dev ecosystem clean-root <pkg>` quarantines into `<repo>/.scitex/dev/runtime/root-violations/<ts>/`. Legitimate exceptions go in `audit.root-whitelist` of `.scitex/dev/config.yaml`.
- **Naked `src/` next to a real package layout** — pick one. SciTeX packages always use `src/<package_name>/`.
- **`tests/` that doesn't mirror `src/`** — see [02_package/06_project-structure-tests.md](06_project-structure-tests.md).
- **Examples with no `_out/`** — readers can't see what the demo produces. See [02_package/05_project-structure-examples.md](05_project-structure-examples.md).
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.
- **Importing the umbrella `scitex` from `src/` of a scitex-* package** — see [02_package/02_project-structure-src.md](02_project-structure-src.md).

## Pre-release / major-review checklist

- [ ] Every `src/.../*.py` has a corresponding `tests/.../test_*.py` (or documented exception)
- [ ] Every example has a tracked `_out/` and a `tests/examples/test_*.py`
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.dev/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
- [ ] No `scitex` umbrella import in `src/` (see [02_package/02_project-structure-src.md](02_project-structure-src.md))
- [ ] `scitex-dev ecosystem audit-project <distribution>` shows no violations
- [ ] All five required community files at root (PS-133/134/135/137/138):
      `README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CLA.md`
- [ ] `examples/` exists with at least one runnable file (PS-136)
