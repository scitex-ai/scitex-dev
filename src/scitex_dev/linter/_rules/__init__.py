"""Rule definitions for SciTeX linter.

After the per-package rule migration, the engine ships only the
**cross-cutting** rules that don't fit a single owning package:

- `EH001` — generic Python error-handling lint
- `I001-I007` — import hygiene (engine cross-cuts every package)
- `S001-S008` — structure / `@stx.session` (cross-cuts every package)

Rules that talk about a specific package's API live in that package's
`_linter_plugin.py`:

- `IO001-IO007` → scitex-io
- `PA001-PA005` → scitex-io  (paths talk about `stx.io.save()`)
- `ST001-ST006` → scitex-stats
- `P001-P005`   → figrecipe
- `FM001-FM009` → figrecipe
- `P006-P009`   → figrecipe (style-override kwargs)

`lookup(rule_id)` returns the merged engine + plugin rule for any id.
Plugin entries win on collision so leaf packages can override engine
defaults if needed.
"""

from ._base import Rule
from ._error_handling import EH001
from ._lookup import lookup
from ._lookup import reset as reset_lookup_cache  # noqa: F401

ALL_RULES = {EH001.id: EH001}

SEVERITY_ORDER = {"error": 2, "warning": 1, "info": 0}

__all__ = ["Rule", "ALL_RULES", "SEVERITY_ORDER", "lookup", "reset_lookup_cache", "EH001"]
