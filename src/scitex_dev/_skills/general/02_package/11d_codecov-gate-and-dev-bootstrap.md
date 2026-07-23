---
description: |
  [TOPIC] CI and Codecov — the hard coverage gate, dev-bootstrap deps, and workflow merge
  [DETAILS] The optional `--cov-fail-under=90` pre-upload guard (adopt only once already ≥90%); the rule that `[dev]` extras MUST install every marker-providing / collector package the suite uses (pytest-asyncio, fastmcp) or tests silently no-op or skip; the test-file `pytest.importorskip` requirement for optional deps (else collection aborts the whole run); merging the redundant `Test` + `Install Test` badges into one `test.yml`; and the `tests/integration/<mirror>/` placement for `_real.py` tests to satisfy PS-204. Companion to [11_ci-and-codecov.md](11_ci-and-codecov.md).
tags: [scitex-general-package-ci-codecov]
---

# Codecov — the hard gate, dev-bootstrap, and workflow merge

> Parent leaf: [`11_ci-and-codecov.md`](11_ci-and-codecov.md).

## Hard `--cov-fail-under` gate (optional)

The Codecov `coverage.status.project.target` setting is the primary
gate; it runs after the upload and posts a check on PRs. For an
additional pre-upload guard, add `--cov-fail-under=90` to the pytest
invocation:

```yaml
- name: Run tests with coverage
  run: |
    python -m pytest "$GITHUB_WORKSPACE/tests/" -v --tb=short --timeout=120 \
      --cov=src/${{ steps.pkg.outputs.import_name }} \
      --cov-report=xml --cov-report=term \
      --cov-fail-under=90
```

Only adopt this once the package is already ≥ 90 %; setting it earlier
just makes CI permanently red.

## Dev-bootstrap MUST install marker-providing packages

The `[dev]` extras (or whatever extras the bootstrap installs) MUST
include every package that registers a pytest marker / collector
plugin the test suite uses. The campaign found two recurring offenders:

- **`pytest-asyncio`** — without it, `@pytest.mark.asyncio` decorated
  tests emit `PytestUnknownMarkWarning` and the coroutine body never
  awaits anything (the test silently "passes" by doing nothing).
- **`fastmcp`** — without it, MCP-server tests skip via
  `pytest.importorskip("fastmcp")` and the entire MCP surface goes
  un-exercised in CI; the badge is green for the wrong reason.

Both belong in `[project.optional-dependencies].dev` (or `.test`, if
the package splits them) and must be installed by every CI workflow
that runs `pytest tests/`. Verify with:

```bash
.venv/bin/python -c "import pytest_asyncio, fastmcp; print('ok')"
```

If this fails after `pip install -e .[dev]`, the extras are missing the
package. Add it; do not paper over with a workflow-level
`pip install pytest-asyncio` — the dev-bootstrap is the source of
truth for "everything a developer needs to run the suite".

The bootstrap gap manifests as confusing
`PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` lines in the
CI log; that warning is the symptom of this rule being violated.

## Test-file imports of optional deps must `pytest.importorskip`

Any `import <optional-dep>` at module top of a test file MUST be
guarded:

```python
import pytest
h5py = pytest.importorskip("h5py")
```

Otherwise the test module fails at *collection* if the optional dep is
absent, which silently aborts ALL tests in that pytest run — coverage
upload never happens, masking the real state of every other test in the
package.

This is the contract Codecov assumes. Rule code reserved: **PA-303**
(see `03_interface/01_python-api/TODO.md`).

## Merge `Test` + `Install Test` into one workflow

Two badges saying "tests pass" is redundant. Keep both jobs but
collapse them into a single `test.yml`:

```yaml
jobs:
  test:                  # the existing pytest matrix
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps: [...]

  install-check:         # what install-test.yml currently does
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: |
          python -m venv .venv
          .venv/bin/pip install -e .
          .venv/bin/python -c "import <import_name>"
```

One workflow → one badge → one re-run button. Delete the old
`install-test.yml`. Update the README badge block to remove the second
Tests row.

## `tests/integration/<mirror>/` for `_real.py` tests

PS-204 (orphan test file) flags `tests/<pkg>/<mirror>/test_X_real.py`
because there is no `src/<pkg>/<mirror>/_X_real.py` to mirror. The
`_real` suffix is the SciTeX convention for "integration test with
real I/O, no mocks" — a deliberate sibling of `test_X.py`. Two clean
ways to satisfy both conventions:

1. **Move** to `tests/integration/<mirror>/test_X_real.py`. PS-204 only
   scans `tests/<pkg>/<mirror>/`, so the orphan rule doesn't fire and
   pytest still collects them via `tests/`.
2. **Merge** the contents into `tests/<pkg>/<mirror>/test_X.py` as a
   `class TestIntegration:` block. Heavier rewrite; only worth it when
   the file is small.

Add `__init__.py` to each new `tests/integration/<mirror>/` directory
so pytest's rootdir-import mode disambiguates basename collisions
(e.g. two `test__zarr_real.py` under different mirror dirs).
