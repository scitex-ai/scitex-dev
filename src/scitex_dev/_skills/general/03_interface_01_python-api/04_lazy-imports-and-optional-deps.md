---
name: interface-python-api-lazy-imports
description: Optional dependencies must use lazy imports — `try: from ._mod import X except ImportError: X = None` — so a missing extra never crashes import. Conditional `__all__` rules. The `_LazyModule` class for the umbrella's submodule attribute access. Sentinel pattern for "feature available?" checks.
tags: [scitex-python, scitex-general, scitex-package, meta]
---

# Lazy Imports and Optional Dependencies

## Rule: a missing optional dep never crashes `import <pkg>`

Use the canonical helper from scitex-dev. **Shipped in `scitex_dev._imports`** (re-exported as `from scitex_dev import try_import_optional`). Signature: `try_import_optional(module_path, attr=None, *, extra=None, pkg=None, package=None)` — returns the imported object or `None` on `ImportError` / missing attribute. Failed imports record an `InstallHint` retrievable via `last_install_hint(name)`.

```python
# ✅ Canonical pattern
from scitex_dev import try_import_optional

H5Explorer   = try_import_optional("._h5_explorer",   "H5Explorer",   extra="h5",   pkg="scitex-io")
ZarrExplorer = try_import_optional("._zarr_explorer", "ZarrExplorer", extra="zarr", pkg="scitex-io")
```

Returns the imported object on success, `None` on `ImportError`. Records `(extra, pkg)` so a use-site error message can render `pip install scitex-io[h5]` without each call site hand-spelling it.

The names appear in `__all__` either way (set to `None` if unavailable). User code probes them:

```python
import scitex_io as sio
if sio.H5Explorer is None:
    raise RuntimeError("Install scitex-io[h5] to use H5Explorer")
explorer = sio.H5Explorer(...)
```

### Why a helper instead of inline `try/except`?

- Eliminates the 3-line × N-optional-deps boilerplate in every `__init__.py`.
- Standardizes the install-hint shape — `audit-api` can grep one call signature instead of parsing `try/except` ASTs.
- One place to evolve the behavior (e.g. emit a warning at import time, log to telemetry) without touching every package.
- scitex-dev is a hard runtime dep for every standalone (light: `scitex-config` + `tomli`); the helper is always importable.

### Legacy `try/except` form (still tolerated, not preferred)

```python
# Pre-helper era — still works, drift to migrate
try:
    from ._h5_explorer import H5Explorer
except ImportError:
    H5Explorer = None
```

Migrate when touching the file for other reasons; don't churn just to convert.

## Why `None`-assignment over conditional `__all__`

Two patterns exist in the wild:

| Pattern                                  | Behavior                                                                 |
|------------------------------------------|--------------------------------------------------------------------------|
| **A. `Item = None` + always in `__all__`** ⭐ | `dir()` always shows `H5Explorer`. `hasattr(pkg, "H5Explorer")` is `True`. Users probe with `is None`. |
| B. Conditional `__all__.append("Item")`  | `dir()` hides `H5Explorer` when missing. `hasattr` is `False`. Users probe with `hasattr`.            |

**Canonical: A.** Reasons:

- `dir()` output is stable across installs — easier debugging when comparing two environments.
- The name being a callable check (`is None`) is more discoverable than `hasattr`.
- Linters and IDEs can resolve the name even when the optional dep is missing.

Pattern B exists in some packages — drift to fix.

## Public availability flags

For binary "is this feature available" questions, expose a boolean alongside (opt-in — only when the optional dep gates a major feature surface):

```python
ScholarSession = try_import_optional(
    "._scholar_runtime", "ScholarSession",
    extra="scholar", pkg="scitex-scholar",
)
SCHOLAR_AVAILABLE = ScholarSession is not None

__all__ = ["ScholarSession", "SCHOLAR_AVAILABLE", ...]
```

User code:

```python
import scitex_scholar as ssch
if ssch.SCHOLAR_AVAILABLE:
    ...
```

Use these sparingly — only when the optional dep gates a major feature surface, not a single function.

## What goes in `extras_require`

- `pyproject.toml` declares optional groups: `[project.optional-dependencies]` → `h5 = ["h5py>=3"]`.
- `pip install scitex-io[h5]` installs the group.
- The skill leaf [01_ecosystem_02_dependency-and-version-pinning.md](../01_ecosystem_02_dependency-and-version-pinning.md) covers extras naming + pinning.

## The umbrella's `_LazyModule`

`scitex/__init__.py` uses `_LazyModule` to expose `scitex.io`, `scitex.stats`, etc. without importing them eagerly:

```python
# scitex/__init__.py (abbreviated)
class _LazyModule:
    def __init__(self, dist_name, import_name):
        self._dist_name = dist_name
        self._import_name = import_name
        self._module = None

    def __getattr__(self, name):
        if self._module is None:
            try:
                self._module = importlib.import_module(self._import_name)
            except ImportError as e:
                raise ImportError(
                    f"Install {self._dist_name} to use scitex.{name}"
                ) from e
        return getattr(self._module, name)

io = _LazyModule("scitex-io", "scitex_io")
stats = _LazyModule("scitex-stats", "scitex_stats")
```

Why:

- `import scitex` stays cheap — no eager load of every standalone.
- Users who only need `scitex.io` don't pay for `scitex.stats` import.
- A missing standalone surfaces a helpful error pointing at the right `pip install`.

Per-package implementations should NOT reinvent `_LazyModule` — the umbrella owns it. Standalones use the simple `try/except ImportError` pattern above.

## Anti-patterns

```python
# ❌ Top-level import of optional dep — crashes whole package
from h5py import File   # ImportError if h5py not installed

# ❌ Importing inside a function silently ignores missing dep
def explore(path):
    import h5py   # NameError surfaces only when explore() is called
    return h5py.File(path)

# ❌ Re-raising as a different error type loses the install hint
try:
    import h5py
except ImportError:
    raise RuntimeError("h5py needed")   # User sees 'RuntimeError', not 'pip install ...'
```

## Audit

- Every `try: from ... except ImportError` that gates a public name → must assign `None`.
- Every conditional public name → must be in `__all__`.
- No top-level `import <optional_dep>` outside a try/except.

Linter rule (planned): **PA007** — flag bare imports of names declared in `extras_require`.
