---
description: |
  [TOPIC] Interface Python Api Lazy Imports
  [DETAILS] Two lazy-import concerns — (1) optional deps via `try_import_optional` (always `extra="all"` — per-feature extras are retired) so a missing optional dep never crashes import, and (2) PEP 562 `__getattr__` so heavy required submodules don't slow down `import <pkg>` and CLI startup. Conditional `__all__` rules. The `_LazyModule` class for the umbrella's submodule attribute access. Sentinel pattern for "feature available?" checks.
tags: [scitex-general-interface-python-api-lazy-imports-and-optional-deps]
---

# Lazy Imports and Optional Dependencies

This file covers two related but distinct concerns:

1. **Optional dependencies** (sections below up to "Audit") — handling `pip install "pkg[all]"` gates so a missing optional dep doesn't crash `import pkg`.
2. **PEP 562 startup-time lazy imports** (final section) — making `import pkg` cheap when all required deps ARE installed but submodules transitively load heavy code.

Both are "lazy imports"; they solve different problems and use different mechanisms. Don't conflate them.

## Rule: a missing optional dep never crashes `import <pkg>`

Use the canonical helper from scitex-dev. **Shipped in `scitex_dev._imports`** (re-exported as `from scitex_dev import try_import_optional`). Signature: `try_import_optional(module_path, attr=None, *, extra=None, pkg=None, package=None)` — returns the imported object or `None` on `ImportError` / missing attribute. Failed imports record an `InstallHint` retrievable via `last_install_hint(name)`.

```python
# ✅ Canonical pattern
from scitex_dev import try_import_optional

# `extra` is ALWAYS "all" — it is the only extra that exists (see below).
H5Explorer   = try_import_optional("._h5_explorer",   "H5Explorer",   extra="all", pkg="scitex-io")
ZarrExplorer = try_import_optional("._zarr_explorer", "ZarrExplorer", extra="all", pkg="scitex-io")
```

Returns the imported object on success, `None` on `ImportError`. Records `(extra, pkg)` so a use-site error message can render `pip install scitex-io[all]` without each call site hand-spelling it.

*(Amended 2026-08-31 — these examples used to pass `extra="h5"` / `extra="zarr"`. Per-feature extras are retired; `extra="all"` is the only correct value. The parameter stays because the rendered hint still needs it.)*

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

## What goes in the `all` extra

- `pyproject.toml` declares **exactly one** extra: `[project.optional-dependencies]` → `all = [..., "h5py>=3", ...]`, organised with comments.
- `pip install "scitex-io[all]"` installs it. That is the only install line a user ever needs, and the only one any error message should print.
- There is **no** `[h5]`, `[zarr]`, `[parquet]`, … — per-feature extras are retired by operator ruling 2026-08-31. An optional dep is still optional; it just no longer gets its own name.
- `dev` / `docs` are PEP 735 `[dependency-groups]`, not extras, and never reach consumers.
- Rule, rationale, the three measured facts and the migration cost: [01_ecosystem/26_the-only-extra-is-all.md](../../01_ecosystem/26_the-only-extra-is-all.md). Pinning: [01_ecosystem/02_dependency-and-version-pinning.md](../../01_ecosystem/02_dependency-and-version-pinning.md).

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

## See also (split out to keep this file under the size cap)

- Optional-dependency **audit** rules + the `pytest.importorskip` test-side counterpart → [15_optional-deps-audit.md](15_optional-deps-audit.md)
- **PEP 562** module `__getattr__` for startup-time speed (the "final section" referenced in the intro) → [16_pep562-startup-lazy-imports.md](16_pep562-startup-lazy-imports.md)
