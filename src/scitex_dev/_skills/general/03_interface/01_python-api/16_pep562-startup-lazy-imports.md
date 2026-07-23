---
description: |
  [TOPIC] Interface Python Api PEP 562 Startup Lazy Imports
  [DETAILS] PEP 562 module `__getattr__` for startup-time speed — even when all required deps are installed, eager submodule imports in `__init__.py` make `import <pkg>` slow, and every CLI invocation pays that cost. The `_LAZY_ATTRS` map pattern, compatibility with `try_import_optional` (gating vs deferring), what it means for submodules, common mistakes, the cold-start audit recipe, and the PA-008 auditor.
tags: [scitex-general-interface-python-api-pep562-startup-lazy-imports]
---

## PEP 562 module `__getattr__` for startup-time speed

Split out from [04_lazy-imports-and-optional-deps.md](04_lazy-imports-and-optional-deps.md); "above" below refers to the optional-deps patterns in that router file.

The patterns above solve "missing optional dep". This section solves a different problem: **even when all required deps are installed, eager submodule imports in `__init__.py` make `import <pkg>` slow.** That cost is paid by every CLI invocation, every shell tab-completion, every quick script.

### Rule

**Top-level `<pkg>/__init__.py` MUST NOT contain `from .X import a, b, c` for heavy submodules.** Public names are exposed via PEP 562 `__getattr__` and loaded on first attribute access.

A "heavy" submodule is anything that transitively imports the `scitex` umbrella, `scitex_config`, `scitex_scholar`, `figrecipe`, `torch`, `numpy`, or any package whose own import takes >50ms in a fresh interpreter.

### Why

Every Click CLI invocation pays the full `import <pkg>` cost — *before any command runs*. Shell tab-completion calls the program once per Tab press. A 9-second `import scitex_dev` made `scitex-dev <Tab>` unusable.

After lazy refactor (scitex-dev 0.10.1):

| Measurement                | Before | After  |
|----------------------------|--------|--------|
| `import scitex_dev`        | 8.4s   | 0.14s  |
| `scitex-dev --help`        | 9.4s   | 0.26s  |
| Tab press in `scitex-dev …`| ~9s    | <0.5s  |

### Pattern

```python
# pkg/__init__.py
from __future__ import annotations

# Cheap things only — no `from .X import Y` for heavy submodules.
from importlib.metadata import PackageNotFoundError, version as _v
try:
    __version__ = _v("pkg")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

# Public-name → source-submodule map. ONE row per public symbol.
_LAZY_ATTRS: dict[str, str] = {
    "wrap_as_cli": "cli_utils",
    "load_config": "config",
    "ECOSYSTEM": "ecosystem",
    # ... add a row each time you'd previously have written `from .X import Y`.
}


def __getattr__(name: str):
    """PEP 562 lazy-loader: import on first access, cache, return."""
    mod_name = _LAZY_ATTRS.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    attr = getattr(import_module(f".{mod_name}", __name__), name)
    globals()[name] = attr  # cache; subsequent access skips this branch
    return attr


def __dir__() -> list[str]:
    return sorted(set(_LAZY_ATTRS) | set(globals()))


__all__ = list(_LAZY_ATTRS) + ["__version__"]
```

Behavior:

- `from pkg import foo` → triggers `__getattr__("foo")` → imports submodule once, caches.
- `pkg.foo` → same path.
- `dir(pkg)` → reports all lazy names without loading them.
- `import pkg` alone → does NOT load any submodule. **This is the win.**

### Compatibility with `try_import_optional`

The two patterns compose. For an optional submodule (gated by an extra):

```python
# Eager — current pattern from earlier in this file. Costs are bounded by
# what try_import_optional touches, which should be just the import attempt.
H5Explorer = try_import_optional(
    "._h5_explorer", "H5Explorer", extra="h5", pkg="scitex-io"
)
```

`try_import_optional` is for **gating**, not for **deferring**. If the optional submodule is heavy, deferring its import via `__getattr__` is appropriate; if it's light, eager `try_import_optional` is fine.

### What this means for submodules

Submodules can keep eager imports — only the **top-level** `__init__.py` matters for CLI startup. A `pkg.config` module can `import yaml` at the top; what matters is that `import pkg` does not transitively load `pkg.skills` → `pkg.test_runner` → the umbrella.

### Common mistakes

| Anti-pattern                                         | Why it's wrong                                                      |
|------------------------------------------------------|---------------------------------------------------------------------|
| `from .skills import verify_X` at module top         | `skills/` may pull `figrecipe` or umbrella; defer to `_LAZY_ATTRS`. |
| `from .test_runner import run_local` at module top   | `test_runner` likely depends on heavy testing infra.                |
| `import scitex` at module top of any submodule consumed by the CLI | Drags the umbrella into every CLI call. |
| `from .types import Result` at module top ✓          | OK — `types.py` should be a pure-stdlib leaf module.                |

### Audit recipe

```bash
# Should be < 500ms in a fresh interpreter.
python -c "import time; t=time.perf_counter(); import <pkg>; print(f'{(time.perf_counter()-t)*1000:.0f}ms')"

# Or with breakdown of who pulls in what:
python -X importtime -c "import <pkg>" 2>&1 | sort -k2 -nr | head -20
```

If `import <pkg>` cold-start is > 500ms, top-level `__init__.py` is leaking eager imports. Convert them to `_LAZY_ATTRS` rows.

### Auditor

`scitex-dev ecosystem audit-project <pkg>` will flag heavy top-level imports as rule **PA-008** (TBD). The check measures `import <pkg>` cold-start time and fails if > 500ms; remedy points to this section.

### Audited

- `scitex-dev` 0.10.1 — refactored 8.4s → 0.14s. PR #?? (link to follow).
- `scitex` umbrella — already lazy via `_LazyModule` (see "The umbrella's `_LazyModule`" section above). Different mechanism (proxies whole subpackages by name), same intent.
