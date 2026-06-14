---
description: |
  [TOPIC] Pre-push gate — CI-vs-gate coverage principle
  [DETAILS] What the canonical pre-push gate covers (lightweight, diff-scoped checks: audit-all + ruff F401/F811 + import-smoke + scope tests) vs what stays CI-only by design (pytest-matrix, sphinx-docs, codecov, ecosystem-audit whole-repo). The gate's purpose is to stop the push → red → patch → push merry-go-round; CI's purpose is the thorough matrix.
tags: [scitex-dev-pre-push-gate]
---

# Pre-push gate — coverage principle

> **The pre-push gate covers CI's LIGHTWEIGHT checks (ruff F401/F811 +
> audit-all + import-smoke) on the CHANGED diff. Heavy CI items
> (pytest-matrix, sphinx-docs, codecov, ecosystem-audit whole-repo)
> remain CI-only by design.**

The canonical gate script ships at
`src/scitex_dev/_hooks/pre-push.sh` and is distributed via the same
symlink mechanism as `run_lint.sh` (Pillar-0 anti-drift). Operators
enable it per-repo with:

```bash
scitex-dev hooks enable-pre-push --target ~/proj/<package>
```

## What the gate runs (lightweight subset)

| Step       | What                                              | Scope                  |
|------------|---------------------------------------------------|------------------------|
| `[1/4]`    | `scitex-dev ecosystem audit-all <pkg>`            | whole-repo             |
| `[2/4]`    | `ruff check --select F401,F811`                   | CHANGED `.py` only     |
| `[3/4]`    | `import-smoke` — `importlib.import_module(...)`   | CHANGED `src/` only    |
| `[4/4]`    | `pytest --testmon -m "not slow and not integration"` | testmon-scoped       |

Time budget: 60 s total (`SCITEX_DEV_PREPUSH_TIMEOUT` to override).

## What stays CI-only (heavy / matrix)

These intentionally do NOT run in the gate — they would either blow
the 60 s budget or duplicate matrix coverage that only makes sense
in CI:

- `pytest-matrix` (Python 3.11 / 3.12 / 3.13 cross-product)
- `rtd-sphinx-build` (full docs build)
- `codecov` upload (CI is the single source of coverage truth)
- `ecosystem-audit` whole-repo nightly run (CI runs against every
  package's clone; the gate runs `audit-all` for the current repo
  only)
- `auto-merge`, `cla`, `pypi-publish`, `sync-main` (release/admin
  workflows — no operator value running locally)

## Diff-scoping is the design principle

Every gate step that CAN be scoped to `git diff` IS scoped. The gate
computes the changed-file list once at startup:

```bash
git diff --name-only --diff-filter=AM @{upstream}..HEAD -- '*.py'
```

with a fallback to `origin/HEAD..HEAD` when no upstream is set.

- **ruff** runs only against changed `.py` files.
- **import-smoke** imports only modules whose source files changed.
- **testmon** already follows the diff (pytest-testmon is diff-aware).
- **audit-all** is whole-repo today; per-package scoping is tracked
  as a follow-up.

If there are no changed `.py` files (e.g. README-only push), ruff
and import-smoke print INFO+SKIPPED — no false positives, no false
greens.

## Drift detection: PS-185

The auditor rule `PS-185` (slug `gate-covers-ci-lightweight`) reads
`.github/workflows/*.yml` AND the canonical gate script and flags any
lightweight CI job the gate is missing. Heavy items are exempt via:

1. The hard-coded `HEAVY_EXEMPT` set (pytest, sphinx, codecov,
   ecosystem-audit, etc.).
2. A per-workflow `# PS-185-exempt: <reason>` comment marker in the
   first 40 lines of the YAML.

This stops the inverse failure mode: CI adds a new lightweight check,
the gate doesn't follow, and operators silently lose local feedback.

## See also

- `docs/sphinx/pre_push_gate.rst` — Sphinx reference page (CLI + bypass).
- `src/scitex_dev/_cli/audit/_project/_check_gate_coverage.py` — PS-185.
- `src/scitex_dev/_hooks/pre-push.sh` — the gate script itself.
