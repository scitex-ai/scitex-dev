---
name: package-project-structure
description: Canonical top-level repo layout for a SciTeX *package* — what belongs in `src/`, `tests/` (mirror discipline + public/private naming with double-underscore for private), `examples/` (numbered with `_out/` committed + matching `tests/examples/test_*.py`), `scripts/` (maintenance/research, not shipped), `references/` (read-only external material with version pins), `templates/`/`assets/` (wheel-vs-git payload separation pattern), what's allowed at the repo root (pyproject.toml-only — no setup.py/requirements.txt/MANIFEST.in), Makefile target inventory, anti-patterns, pre-release checklist, and the rule that a SciTeX package's own `src/` must NOT depend on `scitex` (would create a circular ecosystem dependency). For *research-project* layout (`./config`, `./data`, `./mgmt`, `SDIR_OUT`/`SDIR_RUN`), see [`../scientific/02_research-project_01_project-structure.md`](../scientific/02_research-project_01_project-structure.md).
tags: [scitex-python, scitex-general, scitex-package, project-structure, layout, meta]
---

# Package Project Structure

The canonical layout for a SciTeX **package** repo. A clean codebase is one
a stranger could publish today without an apology — every directory has one
purpose, every file is in the right directory, nothing half-finished sits
where finished work should be.

> Building a *research project* (analysis pipelines, experiments) instead of
> a package? See [`../scientific/02_research-project_01_project-structure.md`](../scientific/02_research-project_01_project-structure.md).

## Top-level directories

### `./src` — pip-installable package

- The production package — everything here ships in the wheel.
- One package per repo: `<repo>/src/<package_name>/...`.
- Imports are absolute (`from <package_name>.x.y import z`), never `from src...` and never relative across package boundaries.
- Inter-package deps follow the **cascade direction** (see [01_ecosystem_01_upstream-and-downstream.md](01_ecosystem_01_upstream-and-downstream.md)): a downstream package importing from an upstream one is fine and common (e.g. `scitex-stats` → `scitex-io`). What `src/` should **not** import is the umbrella `scitex` package — that re-exports the package itself and creates a real cycle. Tests, scripts, and examples are free to import from the umbrella.

### `./tests` — mirror of `./src`

Pytest-driven, controlled via `pyproject.toml`. Tests are organized into a small, fixed set of literal subdirectories — **only `<pkg>` is variable**, everything else is a literal name:

| Subdir | Tracked? | Mirrors / contains |
| :--- | :--- | :--- |
| `tests/<pkg>/` | ✅ | 1:1 mirror of `src/<pkg>/` (the bulk of unit tests) |
| `tests/scripts/` | ✅ | mirror of `./scripts/` |
| `tests/examples/` | ✅ | one `test_<example-stem>.py` per file in `./examples/` |
| `tests/skills/` | ✅ | structural tests for shipped `_skills/` (skill linter, layout) |
| `tests/agentic/` | ✅ | agentic-trigger tests — LLM invokes the skill / MCP tool / CLI and we assert the right path fires |
| `tests/integration/` | ✅ | cross-module / cross-package tests |
| `tests/e2e/` | ✅ | end-to-end pipeline tests |
| `tests/github_actions/` | ✅ | local GitHub Actions runner config (`act`/Apptainer) |
| `tests/coverage/` | gitignored | HTML / XML coverage reports (replaces a top-level `./htmlcov/`) |
| `tests/logs/` | gitignored | pytest run logs, captured stdout/stderr |
| `tests/reports/` | optional | agent-generated test summaries |

Large/long tests should target a remote/HPC runner via `dev_test_hpc*` MCP tools rather than blocking local dev.

#### Test-file naming patterns (pip package)

Test paths mirror source paths exactly. The public/private prefix mirrors the source file's leading-underscore convention — **double underscore for private**:

```
src/<pkg>/path/to/public_module.py
tests/<pkg>/path/to/test_public_module.py            # single _

src/<pkg>/path/to/_private_module.py
tests/<pkg>/path/to/test__private_module.py          # double __

src/<pkg>/path/to/PublicClass.py
tests/<pkg>/path/to/test_PublicClass.py

src/<pkg>/path/to/_PrivateClass.py
tests/<pkg>/path/to/test__PrivateClass.py
```

### `./examples` — runnable demos

- Every example must actually work (validated by `./tests/examples/`).
- Numbered prefix is mandatory: `./examples/01_<descriptive-name>.{py,sh,ipynb}`.
- Outputs go alongside as `./examples/01_<descriptive-name>_out/` and are **git-tracked** so users see them on GitHub.
- A few outputs are linked from `README.md` as assets (figures, GIFs).
- `./examples/00_run_all.sh` dispatches every example in a single command — useful both as an end-to-end demo and for CI to regress everything.
- Prefer `.py` scripts over `.ipynb` (better for CI + diffability), unless GitHub-rendering is the point.
- Examples should include agentic demonstrations (MCP-tool prompts, Skills invocation patterns) where the package exposes those interfaces.
- Use SciTeX where applicable: `@stx.session`, `stx.io`, `stx.plt`.

Quick checklist:
- [ ] `./examples/00_run_all.sh` dispatcher exists
- [ ] `./examples/01_<descriptive-name>.{py,ipynb,sh}` numbered
- [ ] `./examples/01_<descriptive-name>_out/` present and committed
- [ ] Each example has a matching `./tests/examples/test_*.py`

### `./scripts` — maintenance or scientific analysis

- Project maintenance + scientific analysis (research scripts, one-off pipelines). **Not shipped.**
- Free to depend on SciTeX, third-party tools, etc.
- Helpers used by multiple scripts go in `./scripts/utils/`.
- Anything that produces a result worth keeping should graduate into `./examples/` (as a demo) or `./src/` (as a public API).

#### `./scripts/makefile/` — Makefile target backing scripts

The root `Makefile` is a thin dispatcher; each target's actual logic lives as one script under `./scripts/makefile/`:

```
./scripts/makefile/install.sh
./scripts/makefile/test-changed.sh
./scripts/makefile/test-full.sh
./scripts/makefile/coverage-html.sh
./scripts/makefile/lint.sh
./scripts/makefile/clean.sh
./scripts/makefile/build.sh
./scripts/makefile/upload-pypi-test.sh
./scripts/makefile/upload-pypi.sh
./scripts/makefile/release.sh
```

Root `Makefile`:

```make
install:        ; @./scripts/makefile/install.sh
test-changed:   ; @./scripts/makefile/test-changed.sh
test-full:      ; @./scripts/makefile/test-full.sh
coverage-html:  ; @./scripts/makefile/coverage-html.sh
# ...
```

Why: each target is independently runnable from the shell, easier to test, easier to share between repos (symlink one script across multiple projects), and the Makefile stops growing into a 200-line shell program. Same script can be invoked manually for debugging without going through `make`.

### `./docs` — human-facing documentation

- README is the entry point; deeper docs live here (`./docs/installation.md`, `./docs/details/<topic>.md`).
- `./docs/sphinx/` — Sphinx source tree (`conf.py`, `index.rst`, `*.rst`/`*.md`). See [`04_docs_02_sphinx.md`](04_docs_02_sphinx.md) for the canonical layout.
- `./docs/sphinx/_build/` — local Sphinx build output. Gitignored.
- `./docs/assets/` — figures, screenshots, diagrams referenced from README and other docs.
- `./docs/to_claude/` — agent context files (guidelines, hooks, examples). **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./GITIGNORED/` — catch-all file-based scratch channel.

#### Production-served Sphinx HTML — bundled inside `src/<pkg>/_sphinx_html/`

For a package's docs to appear on **<https://scitex.ai/apps/docs/>** after `pip install <pkg>`, the **pre-built HTML must ship inside the wheel** — not stay confined to `./docs/sphinx/_build/`. Convention:

```
docs/sphinx/_build/html/        ← LOCAL Sphinx output; gitignored
                                   (source-of-truth, populated by `make docs`)
src/<pkg>/_sphinx_html/         ← BUNDLED in the wheel; copy of the above,
                                   refreshed before each release
```

`scitex_dev.docs.get_docs(package=..., format="html")` resolves in this order:
1. `src/<pkg>/_sphinx_html/` inside the **installed** package (production)
2. `./docs/sphinx/_build/html/` in the **source** repo (dev fallback)

That's how `scitex-cloud/apps/workspace/docs_app/` serves per-package docs at runtime.

Release recipe (typical `scripts/makefile/docs.sh`):

```bash
sphinx-build -b html docs/sphinx docs/sphinx/_build/html
rm -rf src/<pkg>/_sphinx_html
cp -r docs/sphinx/_build/html src/<pkg>/_sphinx_html
```

`pyproject.toml` must include the directory in the wheel:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]
include = ["src/<pkg>/_sphinx_html/**"]
```

When **not** to bundle: package is private/internal, has no Sphinx tree. `_sphinx_html/` is absent and `get_docs(format="html")` returns `None` — scitex.ai/apps/docs/ skips that package gracefully.

### `./templates` / `./docs/assets` — wheel-vs-git payload separation

When a package ships **bulky content** that belongs in git but should NOT bloat the PyPI wheel (e.g. `scitex-template/templates/<id>/` ~22 MB scaffolds, screenshots/diagrams referenced from README), vendor it under `./templates/` or `./docs/assets/`, exclude from the wheel via hatch, and fetch on first use into `~/.scitex/<pkg-short>/cache/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]
# templates/ NOT in the wheel — populated at runtime by a shallow clone
[tool.hatch.build.targets.sdist]
include = ["src/<pkg>", "README.md", "LICENSE", "pyproject.toml"]
```

```python
# src/<pkg>/_cache.py
MONOREPO_URL = "https://github.com/<org>/<pkg>.git"
CACHE_ROOT = Path.home() / ".scitex" / "<pkg-short>" / "cache"

def ensure_cache(branch="main", force_refresh=False):
    if not (CACHE_ROOT / ".git").is_dir() or force_refresh:
        subprocess.run(["git", "clone", "--depth", "1", "--branch", branch,
                        MONOREPO_URL, str(CACHE_ROOT)], check=True)
    return CACHE_ROOT
```

When to use: wheel >1 MB, content updates faster than release cadence, OS-specific binaries hatchling won't ship cleanly.
When NOT to use: anything imported by `src/`, small (<100 KB) static data, content the package can't function without.

Verify wheel after build: `python -m zipfile -l dist/<pkg>-<ver>-py3-none-any.whl | head -20`.

## Hidden / scratch directories

| Dir | Use |
| --- | --- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ src/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |

## Mirror discipline (mandatory)

`./src`, `./tests`, and `./examples` mirror each other. This is the most load-bearing organizational rule:

- A reader who knows where a feature lives in `./src` finds its tests + demo without searching.
- CI can deduce coverage gaps mechanically (any `src/x/y/_Z.py` without a matching `tests/x/y/test__Z.py` is a coverage gap).
- Renames cascade predictably across all three trees.

```
src/<pkg>/feature/_X.py
tests/<pkg>/feature/test__X.py        # private: double underscore
src/<pkg>/feature/Y.py
tests/<pkg>/feature/test_Y.py         # public: single underscore
examples/01_using_X_and_Y.py
tests/examples/test_01_using_X_and_Y.py
```

## What's allowed at the repo root

Only files that **must** be at root:

| File | Purpose |
| :--- | :--- |
| `README.md` | Primary entry point |
| `LICENSE` | License text (`AGPL-3.0-only` for SciTeX — see [01_ecosystem_07_license-and-cla.md](01_ecosystem_07_license-and-cla.md)) |
| `pyproject.toml` | Package metadata + build (no `setup.py`, `requirements.txt`, `MANIFEST.in`) |
| `Makefile` | Thin dispatcher; logic lives in `./scripts/` |
| `.gitignore`, `.gitattributes` | VCS hygiene |
| `CLA.md` | CLA agreement text (referenced by `.github/workflows/cla.yml`) |
| `CONTRIBUTING.md` | Contribution guide referencing the CLA |
| `CLAUDE.md` (optional) | AI-agent context for this repo |
| `CHANGELOG.md` (optional) | Release notes if maintained manually |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason — extend an existing one or use `./.playground/` for one-offs.

### `pyproject.toml` is the only Python packaging file

Don't add `setup.py`, `requirements.txt`, or `MANIFEST.in`. All those concerns belong in `pyproject.toml`. Lint enforced by `E5C5`/`E5C9`/`E5C10`/`E5C11`/`E5C13` in `scitex_dev._pyproject_lint`.

## Canonical Makefile targets

`Makefile` is a thin dispatcher; logic lives in `./scripts/`. Standard inventory:

- `install` — install package + dev deps
- `test-changed` — pytest only on files changed vs `develop`
- `test-full` — full pytest suite (slow; CI-only)
- `coverage-html` — coverage report to `./htmlcov/`
- `ci-container`, `ci-act`, `ci-local` — three flavors of running CI locally
- `lint` — ruff / shellcheck / etc.
- `clean` — remove build/`__pycache__`/`htmlcov`
- `build` — build wheel + sdist into `./dist/`
- `upload-pypi-test`, `upload-pypi` — twine upload to TestPyPI / PyPI
- `release` — version bump + tag + push (+ optionally GitHub release)

## Production-ready always

The main branch must be publishable **today**, regardless of in-flight work:

- Half-finished features are on `feature/<verb>-<object>` branches, never on `main`.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Top-level junk** (`tmp_test.py`, `quick_check.py`, `debug.log`, `untitled.ipynb`) — move to `./.playground/` or delete.
- **Naked `src/` next to a real package layout** — pick one. SciTeX packages always use `src/<package_name>/`.
- **`tests/` that doesn't mirror `src/`** — coverage analysis becomes manual; renames break test discoverability.
- **Examples with no `_out/`** — readers can't see what the demo produces without running it themselves.
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.
- **Importing the umbrella `scitex` from `src/` of a scitex-* package** — that umbrella re-exports the package itself, creating a real cycle. Inter-package deps that follow the cascade direction are fine.

## Pre-release / major-review checklist

- [ ] Every `src/.../*.py` has a corresponding `tests/.../test_*.py` (or documented exception)
- [ ] Every example has a tracked `_out/` and a `tests/examples/test_*.py`
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.playground/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
- [ ] No `scitex` import in `src/` (lint: `E5C5_implicit_deps` would catch other classes; this one is policy)
