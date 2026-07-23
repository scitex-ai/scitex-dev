---
description: |
  [TOPIC] Package Tests — audit-project rules and the sync-tests precedent
  [DETAILS] The `audit-project` rules that enforce the tests layout (PS-201 missing parent, PS-202 missing sub-mirror, PS-203 strict tests-root, PS-204 orphan test with enriched relocate hint, PS-205 wrong prefix, PS-206 placeholder-only, PS-207 empty mirror dir, PS-211/PS-212 smoke/e2e warnings, PS-302 unrecognized subdir, PS-303 example without matching test), and the historical `sync_tests_with_source.sh` precedent (auto-mirror creation, the dropped source-as-comments pattern, the read-only auditor + future `--fix`). Companion to [06_project-structure-tests.md](06_project-structure-tests.md).
tags: [scitex-general-package-project-structure-tests]
---

# Tests — auditor coverage and the sync-tests precedent

> Parent leaf: [`./tests`](06_project-structure-tests.md).

## Auditor coverage

`scitex-dev ecosystem audit-project <distribution>` enforces this layout:

- **PS-201** — missing `tests/<pkg>/` parent
- **PS-202** — `src/<pkg>/<sub>/` has files but no `tests/<pkg>/<sub>/`
- **PS-203** — *strict*: any `test_*.py` at `tests/` root (only `__init__.py` and `conftest.py` allowed)
- **PS-204** — orphan test (no matching `src/<pkg>/<path>/...`); detail
  is *enriched*: when exactly one src file shares the expected basename,
  the violation suggests the relocate target; otherwise it lists the
  files actually present in the mirror dir so you can correlate
- **PS-205** — wrong public/private prefix
- **PS-206** — placeholder-only test (no `def test_` or `class Test`)
- **PS-207** — empty test mirror directory (mirror dir exists but contains
  no `test_*.py`, while the corresponding `src/<pkg>/<sub>/` has source
  files); src-aware so it never flags fixture trees that legitimately have
  no source counterpart
- **PS-211** *(W)* — `tests/smoke/` missing OR the `smoke` pytest marker
  not registered in `pyproject.toml`. Severity warning during ecosystem
  adoption; promoted to error once all packages have a smoke layer.
  Opt-out: `[tool.scitex_dev] no_cli = true`.
- **PS-212** *(W)* — `tests/e2e/` missing OR the `e2e` pytest marker not
  registered. Severity warning during adoption.
  Opt-out: `[tool.scitex_dev] no_e2e = true` (or `no_cli = true`).
- **PS-302** — unrecognized subdir at `tests/` root
- **PS-303** — `examples/<name>` without matching `tests/examples/test_<name>.py`

## Historical: `sync_tests_with_source.sh` and source-as-comments

The legacy `tests/sync_tests_with_source.sh` script (still in `~/proj/scitex-python/`) auto-creates missing test files and mirrors the directory structure. It also **embedded source code as comments** at the bottom of every test file — that pattern is now considered too noisy and should be dropped.

The auditor (`audit-project`) is read-only — it never writes to test files. Future work: a `--fix` flag that does the mirror creation without the comment embedding.
