---
description: |
  [TOPIC] Interface Python Api Optional Deps Audit
  [DETAILS] Audit rules for optional-dependency handling — the `try/except ImportError` → assign `None` requirement, conditional public names in `__all__`, no unguarded top-level optional imports, and migration to `try_import_optional` (PA-302/PA-303/PA-007). The test-side counterpart: `pytest.importorskip` instead of unguarded imports so collection stays green.
tags: [scitex-general-interface-python-api-optional-deps-audit]
---

# Optional Dependency Audit

## Audit

- Every `try: from ... except ImportError` that gates a public name → must assign `None`.
- Every conditional public name → must be in `__all__`.
- No top-level `import <optional_dep>` outside a try/except.
- Inline `try/except ImportError: X_AVAILABLE = False` pairs in **src** → migrate to `try_import_optional`. Rule: **PA-302** (planned).
- Unguarded `import <optional-dep>` at module top of a **test** file → wrap in `pytest.importorskip("<optional-dep>")`. Rule: **PA-303** (planned).

### Test-side counterpart of `try_import_optional`

In source: a missing optional dep returns `None` from the helper and
the gate `<NAME>_AVAILABLE = False` lets callers branch. In tests: the
same dep is gated with `pytest.importorskip("<dep>")` at the top of the
test file.

```python
# tests/scitex_io/_load_modules/test__optuna.py
import pytest
optuna = pytest.importorskip("optuna")

from scitex_io._load_modules._optuna import load_yaml_as_an_optuna_dict
```

If the dep is missing, the whole test module is skipped — pytest
collection succeeds, the rest of the suite still runs, and Codecov
sees a complete `coverage.xml`. An unguarded import fails at
collection instead, which aborts every test in the same pytest run
and silently masks the actual state of the package. PA-303 codifies
this requirement.

Linter rule (planned): **PA-007** — flag bare imports of names declared in `extras_require`.
