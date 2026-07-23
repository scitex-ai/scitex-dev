---
description: |
  [TOPIC] Package Root — PS-103 Strict Whitelist
  [DETAILS] The strict root-whitelist rule for a SciTeX package. PS-102 forbids specific dirs by name; PS-103 flips the polarity — anything at repo root not in the strict baseline, not hidden, and not explicitly whitelisted is a violation. Covers the baseline files/dirs/hidden set, per-pkg / global `audit.root-whitelist` overrides, the three project-types that opt out (`special` / `django` / `deferred`), and the non-destructive `clean-root` cleanup flow. Companion to [01_project-structure-root.md](01_project-structure-root.md).
tags: [scitex-general-package-project-structure-root]
---

# PS-103 — strict root whitelist

> Parent leaf: [`./root`](01_project-structure-root.md) (see its "Forbidden top-level dirs (PS-102)" for the by-name blocklist this rule extends).

PS-102 forbids specific dirs by name. **PS-103** flips the polarity:
**anything at repo root that is not in the strict baseline below, not
hidden (`.*`), and not explicitly whitelisted is a violation.**

The auditor lives at `scitex_dev._cli.audit._project._root_whitelist`
and is called by `scitex-dev ecosystem audit-project <pkg>` (rule
`PS-103`, severity `E`).

### Baseline (allowed everywhere, no config needed)

```
files: README.md, LICENSE{,.md,.txt}, CHANGELOG.md, CLA.md,
       CONTRIBUTING.md, SECURITY.md,
       pyproject.toml, Makefile, CLAUDE.md

dirs:  src, tests, docs, examples, scripts, data, externals,
       dist, build, GITIGNORED

hidden: any `.*`
        (.git, .github, .scitex, .dev, .gitignore, .gitattributes,
         .pre-commit-config.yaml, .readthedocs.yaml, .coverage,
         .env, .env.example, .venv, .pytest_cache, …)
```

This matches the canonical clean layout (see `~/proj/scitex-stats`
as a reference implementation).

### Per-pkg / global overrides

Edge cases — Django frameworks, multi-package monorepos, content-
vending packages — declare their extras explicitly in
`<repo>/.scitex/dev/config.yaml`:

```yaml
audit:
  root-whitelist:
    files: [architecture.svg]            # exact basenames
    patterns: ["screenshot-*.png"]       # fnmatch globs
    dirs: [apps, static, media]          # exact dir basenames
```

The same block in `~/.scitex/dev/config.yaml` (user-level) is
unioned on top — useful for scratch directories you want allowed
across every clone.

No category-based silent exemptions: `dataset`, `template`, etc.
are NOT auto-softened. Each package self-declares.

### Project-type opts out of PS-103

Three project-types skip PS-103 with different semantic intent:

| Type | Meaning | Auditor behaviour | Examples |
| :--- | :--- | :--- | :--- |
| `special` | by-design unconventional layout (no future cleanup expected) | silent skip | `scitex-writer`, `socialia`, `scitex-orochi` (monorepo), `newb` (PyPI-alias monorepo), `scitex-ui` (npm hybrid) |
| `django` | Django framework canonical (`apps/`, `static/`, `media/`, `templates/`, …) | silent skip | `scitex-cloud` |
| `deferred` | "I know it's messy; remind me later" | **emits a `[defer]` warning listing what would have fired**, so the operator has a TODO list ready when revisiting | `scitex` umbrella |

Pick one (or combine, e.g. `[pip, django, deferred]` for a Django
app whose deployment artifacts also need a future cleanup pass).

```yaml
# scitex-writer/.scitex/dev/config.yaml — research layout
project-type:
  - pip
  - special

# scitex/.scitex/dev/config.yaml — umbrella with cleanup TODOs
project-type:
  - pip
  - deferred

# scitex-cloud/.scitex/dev/config.yaml — Django + deferred
project-type:
  - pip
  - django
  - deferred
```

`special` / `django` / `deferred` skip PS-103 only; every other PS
rule still fires under `pip`. Prefer one of these over piling
entries into `audit.root-whitelist` when the layout is stable —
the project-type label communicates *intent*, while the whitelist
just enumerates exceptions.

### Cleaning up an offending root

Ecosystem-wide non-destructive cleanup:

```bash
scitex-dev ecosystem clean-root figrecipe              # preview
scitex-dev ecosystem clean-root figrecipe --yes        # apply
scitex-dev ecosystem clean-root all -j 8 --yes         # bulk

# Moves entries into:
#   <repo>/.scitex/dev/runtime/root-violations/<YYYYmmdd-HHMMSS>/
# (gitignored under §4b — restore by `mv` back; delete after review)
```

The pre-write hook `inhibit_project_root_pollution.sh` calls into
the same `is_allowed_at_root()` helper, so write-time and audit-time
share one rule definition — schemas can't drift.
