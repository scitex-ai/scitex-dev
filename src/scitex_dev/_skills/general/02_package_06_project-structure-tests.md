---
name: package-tests
description: `./tests/` for a SciTeX package — pytest-driven, controlled by `pyproject.toml`. The mandatory `tests/<pkg>/` parent (1:1 mirror of `src/<pkg>/`), allowed sibling subdirs (scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/logs/reports/custom), public/private filename convention with double-underscore for private (`test__foo.py` mirrors `_foo.py`), the small set of "meta tests" allowed at `tests/` root, the `audit-project` rules (PS201–PS206, PS302), and the historical `sync_tests_with_source.sh` precedent. Drop the source-as-comments pattern — it's noise.
tags: [scitex-python, scitex-general, scitex-package, project-structure, tests]
---

# `./tests` — pytest-driven, mirrors `./src`

> Sibling leaves: [`./root`](02_package_01_project-structure-root.md) · [`./src`](02_package_02_project-structure-src.md) · [`./scripts`](02_package_03_project-structure-scripts.md) · [`./scripts/makefile`](02_package_04_project-structure-makefile.md) · [`./examples`](02_package_05_project-structure-examples.md)

## Mandatory `tests/<pkg>/` parent

Every package has a `tests/<pkg>/` parent that mirrors `src/<pkg>/` 1:1. **Even when most tests are flat-by-submodule, the `<pkg>` parent must exist.** Audit rule: `PS201`.

```
src/<pkg>/                          tests/<pkg>/
├── __init__.py                     ├── test___init__.py        (only if needed)
├── foo.py                          ├── test_foo.py             (public → single _)
├── _bar.py                         ├── test__bar.py            (private → double __)
├── _Baz.py                         ├── test__Baz.py            (PascalCase preserved)
└── sub/                            └── sub/
    ├── __init__.py                     ├── test_X.py
    ├── X.py                            └── test__Y.py
    └── _Y.py
```

## Public / private filename convention

A leading underscore in the source marks the module **private**. The mirroring test uses **double underscore** between `test` and the basename to echo the source's leading `_` — making the public/private status visible at a glance. PS205 enforces this.

| Source | Test |
| :--- | :--- |
| `foo.py` | `test_foo.py` |
| `_foo.py` | `test__foo.py` |
| `BarClass.py` | `test_BarClass.py` |
| `_BarClass.py` | `test__BarClass.py` |
| `__init__.py` | (usually no test; `test___init__.py` only if you have a real reason) |

## Allowed `tests/` subdirectories

Tests are organized into a **fixed set of literal subdirectories**. Anything else triggers `PS302`. Only `<pkg>` is variable; everything else is a literal name:

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
| `tests/custom/` | ✅ | legacy: tests with no source counterpart |

## Allowed at `tests/` root (NOT in a subdir)

The auditor (`PS203`) flags loose `test_*.py` files at `tests/` root that should be inside `tests/<pkg>/...`. The exception is a small set of **meta tests** that are legitimately top-level because they test cross-cutting concerns:

```
tests/
├── conftest.py
├── __init__.py
├── test_examples.py                # walks ./examples/, runs each
├── test_skills_quality.py          # via _skills_quality_pytest
├── test_integration.py             # legacy (prefer tests/integration/)
├── test_reproduce.py
├── test_thin_wrapper_consistency.py
├── test_units.py
├── test_api.py
├── test_cli.py
├── test_server.py
├── test___version__.py
├── test___main__.py
├── test__install_guide.py
├── test__optional_deps.py
└── <pkg>/                          # mandatory parent
```

Module-mirror tests like `test_save_load.py`, `test_registry.py`, `test__cache.py` belong **inside** `tests/<pkg>/`, not at `tests/` root.

## Other artefacts

- Large/long tests should target a remote/HPC runner via `dev_test_hpc*` MCP tools rather than blocking local dev.
- `pytest.ini` / `[tool.pytest.ini_options]` lives in `pyproject.toml`.
- `conftest.py` at `tests/` root is fine; subdir-scoped `conftest.py` files (`tests/<pkg>/conftest.py`) are also fine.

## Auditor coverage

`scitex-dev ecosystem audit-project <distribution>` enforces this layout:

- **PS201** — missing `tests/<pkg>/` parent
- **PS202** — `src/<pkg>/<sub>/` has files but no `tests/<pkg>/<sub>/`
- **PS203** — loose `test_*.py` at `tests/` root that should live inside `tests/<pkg>/...`
- **PS204** — orphan test (no matching `src/<pkg>/<path>/...`)
- **PS205** — wrong public/private prefix
- **PS206** — placeholder-only test (no `def test_` or `class Test`)
- **PS302** — unrecognized subdir at `tests/` root
- **PS303** — `examples/<name>` without matching `tests/examples/test_<name>.py`

## Historical: `sync_tests_with_source.sh` and source-as-comments

The legacy `tests/sync_tests_with_source.sh` script (still in `~/proj/scitex-python/`) auto-creates missing test files and mirrors the directory structure. It also **embedded source code as comments** at the bottom of every test file — that pattern is now considered too noisy and should be dropped.

The auditor (`audit-project`) is read-only — it never writes to test files. Future work: a `--fix` flag that does the mirror creation without the comment embedding.
