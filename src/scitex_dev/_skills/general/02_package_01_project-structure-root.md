---
name: package-root
description: What's allowed at the repo root for a SciTeX package — README.md, LICENSE, pyproject.toml (the only Python packaging file — no setup.py / requirements.txt / MANIFEST.in), Makefile (thin dispatcher), .gitignore/.gitattributes, CLA.md / CONTRIBUTING.md (for the CLA gate), and optional CLAUDE.md / CHANGELOG.md. Forbidden top-level dirs (`mgmt`, `references`, `htmlcov`, top-level `assets`, `.playground`). Hidden/scratch (`.dev`, `.old`). The `production-ready always` invariant, anti-patterns, and a pre-release checklist. For each subdirectory, see the sibling leaves (02-06).
tags: [scitex-python, scitex-general, scitex-package, project-structure, root, layout]
---

# Repo Root — Package Project Structure

The repo root contains exactly the files that **must** be there. Everything else lives in a subdirectory.

> Building a *research project* instead of a package? See [`../scientific/02_research-project_01_project-structure.md`](../scientific/02_research-project_01_project-structure.md).
>
> Sub-leaves of this section: [`./src`](02_package_02_project-structure-src.md) · [`./scripts`](02_package_03_project-structure-scripts.md) · [`./scripts/makefile`](02_package_04_project-structure-makefile.md) · [`./examples`](02_package_05_project-structure-examples.md) · [`./tests`](02_package_06_project-structure-tests.md)

## What's allowed at the repo root

| File | Purpose |
| :--- | :--- |
| `README.md` | Primary entry point |
| `LICENSE` | License text (`AGPL-3.0-only` for SciTeX — see [01_ecosystem_07_license-and-cla.md](01_ecosystem_07_license-and-cla.md)) |
| `pyproject.toml` | Package metadata + build (no `setup.py`, `requirements.txt`, `MANIFEST.in`) |
| `Makefile` | Thin dispatcher; logic lives in `./scripts/makefile/` (see [02_package_04_project-structure-makefile.md](02_package_04_project-structure-makefile.md)) |
| `.gitignore`, `.gitattributes` | VCS hygiene |
| `CLA.md` | CLA agreement text (referenced by `.github/workflows/cla.yml`) |
| `CONTRIBUTING.md` | Contribution guide referencing the CLA |
| `CLAUDE.md` (optional) | AI-agent context for this repo |
| `CHANGELOG.md` (optional) | Release notes if maintained manually |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason — extend an existing one or use `./.dev/` for one-offs.

## README badges — coverage is required (PS106)

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
badge satisfies `PS106`. The auditor scans the first ~4 KB of
`README.md`, so the badge has to live near the title — a coverage badge
buried at the bottom is invisible and doesn't count.

If the package doesn't yet upload coverage, set up
[`codecov/codecov-action`](https://github.com/codecov/codecov-action)
in `test.yml` first; the badge will then start showing real numbers
once coverage uploads start arriving.

## `pyproject.toml` is the only Python packaging file

Don't add `setup.py`, `requirements.txt`, or `MANIFEST.in`. All those concerns belong in `pyproject.toml`. Lint enforced by `E5C5`/`E5C9`/`E5C10`/`E5C11`/`E5C13` in `scitex_dev._pyproject_lint`.

## Forbidden top-level dirs

| Top-level dir | Why forbidden | Where it should live |
| :--- | :--- | :--- |
| `./mgmt/` | not used in scitex | (delete) |
| `./references/` | not used in scitex | (delete) |
| `./htmlcov/` | coverage artifacts | `./tests/coverage/` (gitignored) |
| `./assets/` | top-level visual noise | `./docs/assets/` |
| `./.playground/` | collapsed for easier typing | `./.dev/` |

## `./docs` — human-facing documentation

- README is the entry point; deeper docs live here (`./docs/installation.md`, `./docs/details/<topic>.md`).
- `./docs/sphinx/` — Sphinx source tree (`conf.py`, `index.rst`, `*.rst`/`*.md`). See [`04_docs_02_sphinx.md`](04_docs_02_sphinx.md) for the canonical layout.
- `./docs/sphinx/_build/` — local Sphinx build output. Gitignored.
- `./docs/assets/` — figures, screenshots, diagrams referenced from README and other docs.
- `./docs/to_claude/` — agent context files (guidelines, hooks, examples). **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./GITIGNORED/` — catch-all file-based scratch channel.

### Production-served Sphinx HTML — bundled in `src/<pkg>/_sphinx_html/`

For a package's docs to appear on **<https://scitex.ai/apps/docs/>** after `pip install <pkg>`, the **pre-built HTML must ship inside the wheel**. Convention:

```
docs/sphinx/_build/html/        # local Sphinx output; gitignored
src/<pkg>/_sphinx_html/         # bundled in the wheel; refreshed at release
```

`scitex_dev.docs.get_docs(format="html")` resolves first to the in-wheel `_sphinx_html/`, then falls back to local `_build/`. See [04_docs_02_sphinx.md](04_docs_02_sphinx.md) for full release recipe.

## `./templates` — wheel-vs-git payload separation

When a package ships **bulky content** that belongs in git but should NOT bloat the PyPI wheel (e.g. `scitex-template/templates/<id>/` ~22 MB scaffolds), vendor it under `./templates/`, exclude from the wheel via hatch, and fetch on first use into `~/.scitex/<pkg-short>/cache/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]
# templates/ NOT in the wheel — populated at runtime by a shallow clone
```

When NOT to use: anything imported by `src/`, small (<100 KB) static data, content the package can't function without.

## Hidden / scratch directories

| Dir | Use |
| :--- | :--- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ src/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |

## Production-ready always

The main branch must be publishable **today**, regardless of in-flight work:

- Half-finished features are on `feature/<verb>-<object>` branches, never on `main`.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Top-level junk** (`tmp_test.py`, `quick_check.py`, `debug.log`, `untitled.ipynb`) — move to `./.dev/<category>/` or delete.
- **Naked `src/` next to a real package layout** — pick one. SciTeX packages always use `src/<package_name>/`.
- **`tests/` that doesn't mirror `src/`** — see [02_package_06_project-structure-tests.md](02_package_06_project-structure-tests.md).
- **Examples with no `_out/`** — readers can't see what the demo produces. See [02_package_05_project-structure-examples.md](02_package_05_project-structure-examples.md).
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.
- **Importing the umbrella `scitex` from `src/` of a scitex-* package** — see [02_package_02_project-structure-src.md](02_package_02_project-structure-src.md).

## Pre-release / major-review checklist

- [ ] Every `src/.../*.py` has a corresponding `tests/.../test_*.py` (or documented exception)
- [ ] Every example has a tracked `_out/` and a `tests/examples/test_*.py`
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.dev/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
- [ ] No `scitex` umbrella import in `src/` (see [02_package_02_project-structure-src.md](02_package_02_project-structure-src.md))
- [ ] `scitex-dev ecosystem audit-project <distribution>` shows no violations
