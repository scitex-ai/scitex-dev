---
description: |
  [TOPIC] Package Tests
  [DETAILS] `./tests/` for a SciTeX package — pytest-driven, controlled by `pyproject.toml`. The mandatory `tests/<pkg>/` parent (1:1 mirror of `src/<pkg>/`), allowed sibling subdirs (scripts/examples/skills/agentic/integration/e2e/github_actions/coverage/results/logs/reports/custom), public/private filename convention with double-underscore for private (`test__foo.py` mirrors `_foo.py`), the small set of "meta tests" allowed at `tests/` root, the `audit-project` rules (PS-201–PS-206, PS-302), and the historical `sync_tests_with_source.sh` precedent. Drop the source-as-comments pattern — it's noise.
tags: [scitex-general-package-project-structure-tests]
---

# `./tests` — pytest-driven, mirrors `./src`

> Sibling leaves: [`./root`](01_project-structure-root.md) · [`./src`](02_project-structure-src.md) · [`./scripts`](03_project-structure-scripts.md) · [`./scripts/makefile`](04_project-structure-makefile.md) · [`./examples`](05_project-structure-examples.md)
>
> Split-out leaves of THIS section: [layered smoke/e2e testing](06b_tests-layered-smoke-e2e.md) · [integration `_real.py` + optional-dep guards](06c_tests-integration-optional-deps.md)

## Mandatory `tests/<pkg>/` parent

Every package has a `tests/<pkg>/` parent that mirrors `src/<pkg>/` 1:1. **Even when most tests are flat-by-submodule, the `<pkg>` parent must exist.** Audit rule: `PS-201`.

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

A leading underscore in the source marks the module **private**. The mirroring test uses **double underscore** between `test` and the basename to echo the source's leading `_` — making the public/private status visible at a glance. PS-205 enforces this.

| Source | Test |
| :--- | :--- |
| `foo.py` | `test_foo.py` |
| `_foo.py` | `test__foo.py` |
| `BarClass.py` | `test_BarClass.py` |
| `_BarClass.py` | `test__BarClass.py` |
| `__init__.py` | (usually no test; `test___init__.py` only if you have a real reason) |

## Allowed `tests/` subdirectories

Tests are organized into a **fixed set of literal subdirectories**. Anything else triggers `PS-302`. Only `<pkg>` is variable; everything else is a literal name:

| Subdir | Tracked? | Mirrors / contains |
| :--- | :--- | :--- |
| `tests/<pkg>/` | ✅ | 1:1 mirror of `src/<pkg>/` (the bulk of unit tests) |
| `tests/scripts/` | ✅ | mirror of `./scripts/` |
| `tests/examples/` | ✅ | one `test_<example-stem>.py` per file in `./examples/` |
| `tests/develop/` | ✅ | **canonical** home for auto-generated scitex-dev gate tests (audit conformance + skills quality). Replaces the deprecated `tests/skills/`. |
| `tests/skills/` | deprecated | legacy structural tests for shipped `_skills/` — migrate into `tests/develop/`. `tests/integration/test_audit_conformance.py` was a duplicate of the develop-gate audit and has been **deleted**. |
| `tests/agentic/` | ✅ | agentic-trigger tests — LLM invokes the skill / MCP tool / CLI and we assert the right path fires |
| `tests/integration/` | ✅ | Python-level cross-module / cross-package tests |
| `tests/smoke/` | ✅ | **fast (<60s)** subprocess-driven CLI happy-path tests; marker `smoke`; runs on every PR (PS-211) |
| `tests/e2e/` | ✅ | **mandatory** end-to-end workflows against real subsystems; marker `e2e`; **runs on every PR by default** — NOT gated by `RUN_E2E=1`. Per-test `pytest.mark.skipif` only when a specific subsystem (apptainer, fastmcp, GPU, NAS) is missing on the runner. (PS-212) |
| `tests/github_actions/` | ✅ | local GitHub Actions runner config (`act`/Apptainer) |
| `tests/coverage/` | gitignored | HTML / XML coverage reports (replaces a top-level `./htmlcov/`) |
| `tests/results/` | gitignored | general test-run artifacts spanning topics (coverage data files, captured payloads, fixture output) |
| `tests/logs/` | gitignored | pytest run logs, captured stdout/stderr |
| `tests/reports/` | optional | agent-generated test summaries |
| `tests/custom/` | ✅ | legacy: tests with no source counterpart |

## Allowed at `tests/` root (NOT in a subdir) — strict

`PS-203` is **strict**: the only files allowed directly at `tests/` root
are pytest infrastructure files. Every test file must live in one of the
allowed subdirectories — there is no "meta test" exemption.

```
tests/
├── __init__.py            # OK
├── conftest.py            # OK
├── <pkg>/                 # required mirror parent
├── examples/              # cross-cutting tests live here
├── integration/
├── e2e/
└── ...
```

Where the old "meta tests" go now:

| Old `tests/test_*.py` | New home |
| :--- | :--- |
| `test_examples.py` | `tests/examples/test_run_all.py` |
| `test_integration.py` | `tests/integration/test_<name>.py` |
| `test_skills_quality.py` | `tests/develop/test_quality.py` (canonical; `tests/skills/` is deprecated) |
| `test_cli.py`, `test_api.py`, `test_server.py` | `tests/<pkg>/test_<name>.py` (mirror the src module being driven) |
| `test___version__.py`, `test___main__.py` | `tests/<pkg>/test___version__.py` etc. (they mirror `__version__.py` / `__main__.py`) |
| `test__install_guide.py`, `test__optional_deps.py` | `tests/integration/` or `tests/<pkg>/` depending on what they actually exercise |

If a legitimate exception comes up that doesn't fit any subdir, propose
extending the allowed-subdirs list rather than letting drift back into
`tests/` root — the strict rule keeps the layout reviewable.

## Other artefacts

- Large/long tests should target a remote/HPC runner via `dev_test_hpc*` MCP tools rather than blocking local dev.
- `pytest.ini` / `[tool.pytest.ini_options]` lives in `pyproject.toml`.
- `conftest.py` at `tests/` root is fine; subdir-scoped `conftest.py` files (`tests/<pkg>/conftest.py`) are also fine.

## Integration tests and optional-dep guards

> Moved to its own leaf: [06c_tests-integration-optional-deps.md](06c_tests-integration-optional-deps.md) — the `_real.py` integration-test suffix and its canonical `tests/integration/<mirror>/` placement (out of PS-204 scope), plus the rule that module-top optional-dep imports must `pytest.importorskip` or they abort collection.

## Layered testing convention — `tests/smoke/` and `tests/e2e/`

> Moved to its own leaf: [06b_tests-layered-smoke-e2e.md](06b_tests-layered-smoke-e2e.md) — the four-layer pyramid with per-layer speed budget and CI trigger, the `smoke` / `e2e` markers, the subsystem-aware E2E skip strategy, conftest expectations, and the `no_cli` / `no_e2e` opt-out.

## Auditor coverage and the sync-tests precedent

> Moved to its own leaf: [06d_tests-auditor-coverage.md](06d_tests-auditor-coverage.md) — the `audit-project` rules that enforce this layout (PS-201–PS-207, PS-211/PS-212, PS-302, PS-303) and the historical `sync_tests_with_source.sh` precedent (the dropped source-as-comments pattern; the read-only auditor + future `--fix`).
