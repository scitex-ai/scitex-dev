---
description: |
  [TOPIC] Optional imports must use `try_import_optional`
  [DETAILS] `scitex_dev._core.imports.try_import_optional` is the only sanctioned
  way to import a `[all]`-tier dependency — raw try/except ImportError is
  forbidden ecosystem-wide. Why the helper (install hints via `_HINTS`,
  ecosystem-wide error improvements, grep target), and what happens when a
  package is promoted from `[all]` to hard (the call becomes a plain `import` —
  delete the helper at the call site). Companion to 11_dependency-tiers.md.
tags: [scitex-general-development-dependency-tiers]
---

# Optional imports — the `try_import_optional` helper

## Optional imports must use `try_import_optional`

`scitex_dev._core.imports.try_import_optional` is the **only**
sanctioned way to import a `[all]`-tier dependency. Raw
`try/except ImportError` is forbidden ecosystem-wide.

```python
from scitex_dev import try_import_optional

# Optional torch dep (lives in [all])
torch = try_import_optional("torch", extra="all", pkg="scitex-stats")
if torch is None:
    # Numpy fallback path
    ...

# Optional module + attr
go_eda = try_import_optional(
    "scitex_genai.protocols.go_eda",
    attr="rank_findings",
    extra="all",
    pkg="scitex-app",
)
```

Why the helper instead of try/except:

- Install hint registered in `scitex_dev._core.imports._HINTS` — error
  paths can call `last_install_hint("torch")` to surface
  "pip install scitex-stats[all]" automatically.
- Single helper means error messages improve across the ecosystem
  when scitex-dev releases — no per-package follow-up.
- Grep target: `try_import_optional(` immediately tells readers
  this is an optional dep, while bare `try: import X` is ambiguous.

## When a package gets *promoted* from `[all]` to hard

The try_import_optional call becomes a plain `import` — delete the
helper at the call site. The helper is for *genuinely* optional;
once a dep is mandatory, keeping the helper there is dead theater.

```python
# Before (when scitex-logging was in [all]):
scitex_logging = try_import_optional("scitex_logging", extra="all", pkg="scitex-stats")
if scitex_logging is None:
    import logging as scitex_logging  # stdlib fallback

# After (scitex-logging is hard):
import scitex_logging
```
