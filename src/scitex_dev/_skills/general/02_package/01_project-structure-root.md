---
description: |
  [TOPIC] Package Root
  [DETAILS] What's allowed at the repo root for a SciTeX package — README.md, LICENSE, pyproject.toml (the only Python packaging file — no setup.py / requirements.txt / MANIFEST.in), Makefile (thin dispatcher), .gitignore/.gitattributes, CLA.md / CONTRIBUTING.md (for the CLA gate), and optional CLAUDE.md / CHANGELOG.md. Forbidden top-level dirs (`mgmt`, `project_management`, `references`, `htmlcov`, top-level `assets`, `.playground`). Hidden/scratch (`.dev`, `.old`). The `production-ready always` invariant, anti-patterns, and a pre-release checklist. For each subdirectory, see the sibling leaves (02-06).
tags: [scitex-general-package-project-structure-root]
---

# Repo Root — Package Project Structure

The repo root contains exactly the files that **must** be there. Everything else lives in a subdirectory.

> Building a *research project* instead of a package? See [`../scientific/02_research-project_01_project-structure.md`](../../scientific/02_research-project_01_project-structure.md).
>
> Sub-leaves of this section: [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md) · [`./tests`](06_project-structure-tests.md)
>
> Split-out leaves of THIS section: [PS-103 strict root whitelist](01b_root-whitelist-ps103.md) · [`docs/` + ADRs + `templates/`](01c_root-docs-adr-templates.md)

## What's required at the repo root

The auditor (`scitex-dev ecosystem audit-project <pkg>`) enforces this list — every file below must be present.

| File | Audit code | Purpose |
| :--- | :--- | :--- |
| `README.md` | PS-137 | Primary entry point |
| `LICENSE` (or `LICENSE.md` / `LICENSE.txt`) | PS-138 | License text (`AGPL-3.0-only` for SciTeX — see [01_ecosystem/07_license-and-cla.md](../01_ecosystem/07_license-and-cla.md)) |
| `CHANGELOG.md` | PS-134 | Release notes (Keep-a-Changelog style; new packages start with `[Unreleased]`) |
| `CONTRIBUTING.md` | PS-135 | Contribution guide referencing the CLA |
| `CLA.md` | PS-133 | CLA agreement text (referenced by `.github/workflows/cla.yml`) |
| `pyproject.toml` | PS-101 | Package metadata + build (no `setup.py`, `requirements.txt`, `MANIFEST.in`) |
| `Makefile` | — | Thin dispatcher; logic lives in `./scripts/makefile/` (see [02_package/04_project-structure-makefile.md](04_project-structure-makefile.md)) |
| `.gitignore`, `.gitattributes` | — | VCS hygiene |
| `.claude/CLAUDE.md` (optional, **canonical**) | — | AI-agent context for this repo. Tolerated as bare `CLAUDE.md` at root for back-compat, but **must be gitignored** either way — it carries machine-local agent state. |

Required directories at root:

| Directory | Audit code | Purpose |
| :--- | :--- | :--- |
| `src/<pkg>/` | (implicit) | Package source — see [02_package/02_project-structure-src.md](02_project-structure-src.md) |
| `tests/<pkg>/` | PS-201 | Mirror of `src/<pkg>/` — see [02_package/06_project-structure-tests.md](06_project-structure-tests.md) |
| `examples/` | PS-136 | At least one runnable `<NN_>name.py` / `.ipynb` / `.sh` |
| `docs/` | (recommended) | Sphinx + assets — see [04_docs/02_sphinx.md](../04_docs/02_sphinx.md) |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason — extend an existing one or use `./.dev/` for one-offs.

## README badges — coverage is required (PS-106)

Every `scitex-*` README must surface its **current test coverage** at
the top, alongside the PyPI / docs / build / license badges. Reviewers
and downstream consumers should be able to see at a glance whether the
package is well-tested without diving into CI logs.

Recommended badge line (drop into the existing `<p align="center">`
badge block near the title):

```markdown
[![coverage](https://img.shields.io/codecov/c/github/<owner>/<repo>)](https://codecov.io/gh/<owner>/<repo>)
```

Either the shields.io shorthand (above) or a direct codecov / coveralls
badge satisfies `PS-106`. The auditor scans the first ~4 KB of
`README.md`, so the badge has to live near the title — a coverage badge
buried at the bottom is invisible and doesn't count.

If the package doesn't yet upload coverage, set up
[`codecov/codecov-action`](https://github.com/codecov/codecov-action)
in `test.yml` first; the badge will then start showing real numbers
once coverage uploads start arriving.

## `pyproject.toml` is the only Python packaging file

Don't add `setup.py`, `requirements.txt`, or `MANIFEST.in`. All those concerns belong in `pyproject.toml`. Lint enforced by `REL-5`/`REL-9`/`REL-10`/`REL-11`/`E5C13` in `scitex_dev._pyproject_lint`.

## Forbidden top-level dirs (PS-102)

| Top-level dir | Why forbidden | Where it should live |
| :--- | :--- | :--- |
| `./mgmt/`, `./project_management/` | not used in scitex | (delete) |
| `./references/` | not used in scitex | (delete) |
| `./htmlcov/` | coverage artifacts | `./tests/coverage/` (gitignored) |
| `./assets/` | top-level visual noise | `./docs/assets/` |
| `./.playground/` | collapsed for easier typing | `./.dev/` |
| `./logs/` | runtime artifact | `./GITIGNORED/logs/` (or `./tests/logs/`) and add to `.gitignore` |
| `./catboost_info/` | CatBoost training artifact | gitignore `catboost_info/` |
| `./signatures/` | scratch / signing artifacts | `./GITIGNORED/signatures/` if needed locally |
| `./scitex/` | orphan module dir — confused with package | the real package is `src/<pkg>/`. For runtime state use a hidden `./.scitex/` (e.g. `./.scitex/<pkg>/runtime/logs/`), never a visible `./scitex/`. |
| `./unknown_out/` | `@stx.session` output landed at root | re-run from a script directory, or set `CONFIG.SDIR_RUN`. Move the dir aside if you need to keep it. |

## PS-103 — strict root whitelist

> Moved to its own leaf: [01b_root-whitelist-ps103.md](01b_root-whitelist-ps103.md) — the strict baseline files/dirs/hidden set, per-pkg / global `audit.root-whitelist` overrides, the `special` / `django` / `deferred` project-type opt-outs, and the `clean-root` cleanup flow.

## `./docs`, ADRs, and `./templates`

> Moved to its own leaf: [01c_root-docs-adr-templates.md](01c_root-docs-adr-templates.md) — `./docs` layout, the production-served Sphinx HTML bundled in `src/<pkg>/_sphinx_html/`, Architecture Decision Records (location, template, PS-173), and the `./templates` wheel-vs-git payload separation.

## Hidden / scratch directories

| Dir | Use |
| :--- | :--- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ src/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |

## Production-ready invariant, anti-patterns, and pre-release checklist

> Moved to its own leaf: [01d_root-production-ready-checklist.md](01d_root-production-ready-checklist.md) — the "production-ready always" invariant (main branch publishable today), the root anti-patterns (top-level junk, naked `src/`, non-mirroring `tests/`, examples with no `_out/`, uncategorized `.dev/`, umbrella `scitex` imported from `src/`), and the pre-release / major-review checklist.
