---
description: |
  [TOPIC] Package Tests — integration `_real.py` placement and optional-dep guards
  [DETAILS] The `_real` integration-test suffix and its canonical placement under `tests/integration/<mirror>/` to stay out of PS-204 mirror scope (plus the per-subdir `__init__.py` that disambiguates basename collisions), and the rule that any module-top `import <optional-dep>` in a test file must use `pytest.importorskip` or it fails at collection and silently aborts the run (PA-303; the scitex-io optuna incident). Companion to [06_project-structure-tests.md](06_project-structure-tests.md).
tags: [scitex-general-package-project-structure-tests]
---

# Integration tests and optional-dep guards

> Parent leaf: [`./tests`](06_project-structure-tests.md).

## Integration tests (`_real.py`)

The `_real` suffix denotes integration tests that exercise real I/O
against the same src module that `test_X.py` covers with mocks. PS-204
sees `test_X_real.py` as an orphan because no `_X_real.py` source file
exists, but this is by design.

**Canonical placement** — keep them out of the PS-204 mirror scope:

```
tests/integration/<mirror>/test_X_real.py       # mirrors src/<pkg>/<mirror>/_X.py
```

PS-204 only scans `tests/<pkg>/<mirror>/`, so `tests/integration/`
is silently skipped while `pytest tests/` still collects it.

Each subdirectory of `tests/integration/` needs an `__init__.py` so
pytest's rootdir-import mode disambiguates basename collisions when
two integration files share the same name (e.g. one
`test__zarr_real.py` under `_load_modules` and another under
`_save_modules`).

## Module-top imports of optional deps must `pytest.importorskip`

Any unguarded `import <optional-dep>` at the top of a test file fails
at **collection** if the dep is absent — pytest aborts the run, no
coverage is uploaded, and Codecov shows a stale or empty number.

Required pattern:

```python
import pytest
h5py = pytest.importorskip("h5py")
```

Rule code: **PA-303** (planned). Real-world incident: scitex-io
sat at 79 % on Codecov for weeks because `import optuna` at the top of
two test modules silently blocked collection. Once removed, the
underlying coverage moved 12 pp.
