---
description: |
  [TOPIC] Package Tests — the layered testing pyramid (smoke + e2e)
  [DETAILS] The four test layers (`tests/<pkg>/`, `tests/integration/`, `tests/smoke/`, `tests/e2e/`) with their distinct role, speed budget, and CI trigger. Naming + per-package ceilings (≤8 smoke, ≤5 e2e), the mandatory `smoke` / `e2e` pytest markers registered in pyproject.toml, the subsystem-aware (NOT env-gated) E2E skip strategy, conftest expectations, and the `no_cli` / `no_e2e` opt-out for packages without a CLI. Companion to [06_project-structure-tests.md](06_project-structure-tests.md).
tags: [scitex-general-package-project-structure-tests]
---

# Layered testing — `tests/smoke/` and `tests/e2e/`

> Parent leaf: [`./tests`](06_project-structure-tests.md).

## Layered testing convention — `tests/smoke/` and `tests/e2e/`

The four test layers form a pyramid; each has a distinct role, speed
budget, and CI trigger:

| Layer | Speed | Trigger | What it tests |
| :--- | :--- | :--- | :--- |
| `tests/<pkg>/` | very fast | every PR | unit-level behaviour (mocked I/O OK where guarded) |
| `tests/integration/` | fast/medium | every PR | Python-level cross-module wiring (real objects, no subprocess) |
| `tests/smoke/` | **<60s total** | every PR | subprocess-driven CLI happy paths — `subprocess.run(["<cli>", "...", "--help"])` etc. |
| `tests/e2e/` | slow (minutes) | **every PR** (mandatory) | full workflows against real subsystems (network, GPU, NAS, …); per-test `skipif` only for missing subsystems |

### Naming + budget

- `tests/smoke/test_*.py` — keep tight; **≤8 smoke tests per package** is a
  good ceiling. Smoke is for "the binary launches and the obvious paths
  don't crash", not feature coverage.
- `tests/e2e/test_*.py` — **≤5 workflow tests per package**. Each test
  exercises one realistic end-to-end story.

### Pytest markers (must be registered)

Both markers MUST be declared in `pyproject.toml` so `-m smoke` / `-m e2e`
does not emit `PytestUnknownMarkWarning`:

```toml
[tool.pytest.ini_options]
markers = [
    "smoke: fast CLI happy-path tests (<60s, runs on every PR)",
    "e2e: end-to-end workflows against real subsystems (mandatory on every PR)",
]
```

Apply markers via `pytestmark = pytest.mark.smoke` at module top, or per
test with `@pytest.mark.smoke`.

### E2E skip strategy — subsystem-aware, NOT env-gated

E2E tests are **mandatory**: a bare `pytest` MUST collect and run them.
Earlier drafts of this leaf said E2E was opt-in via `RUN_E2E=1` — that
was wrong. The blanket skip-gate manufactures false confidence (CI is
green because nothing ran) and is removed.

The only legitimate skip is **per-test, keyed to a missing subsystem**:

```python
# tests/e2e/test_<workflow>.py
import shutil
import pytest

pytestmark = pytest.mark.e2e

@pytest.mark.skipif(shutil.which("apptainer") is None,
                    reason="apptainer not installed on this runner")
def test_full_pipeline_runs_against_real_container():
    ...

fastmcp = pytest.importorskip("fastmcp")  # only if dep missing
```

Acceptable skip predicates: missing CLI binary (`shutil.which`), missing
import (`importorskip`), missing GPU (`torch.cuda.is_available()`),
missing network endpoint, missing credential. NOT acceptable: a blanket
`os.environ.get("RUN_E2E")` check.

### Conftest expectations

- `tests/smoke/conftest.py` — fixtures for spinning a tmpdir / fake home;
  no network.
- `tests/e2e/conftest.py` — fixtures only; **no blanket skip gate**. May
  instantiate real clients (NAS, cloud, GPU runners) inside fixtures that
  themselves `pytest.skip(...)` when the subsystem is absent.

### Opt-out for packages without a CLI

Packages with no CLI surface (e.g. a pure-library tool) exempt themselves
from PS-211 (and implicitly PS-212) via pyproject.toml:

```toml
[tool.scitex_dev]
no_cli = true     # exempts PS-211 (and PS-212)
# no_e2e = true   # exempts PS-212 only
```
