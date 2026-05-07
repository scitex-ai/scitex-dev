"""Rule definitions for SciTeX linter — re-export + lazy lookup.

Top-level imports re-export every engine-defined rule for back-compat
(`from scitex_dev.linter.rules import IO001` keeps working).

For rule ids that are no longer defined in the engine (because they
migrated to a leaf-package plugin), `__getattr__` falls through to
`_rules._lookup.lookup()` so existing code paths like `rules.PA003`
keep resolving — they get the plugin's version transparently.

This is what lets the engine drop `_rules/_path.py` (PA migrated to
scitex-io), `_rules/_io.py` (IO already in scitex-io), `_rules/_stats.py`
(ST already in scitex-stats), `_rules/_plot.py` and `_rules/_figure.py`
(P/FM already in figrecipe) without breaking the checker.
"""

from __future__ import annotations

__all__ = ["ALL_RULES", "Rule", "SEVERITY_ORDER"]

from ._rules import ALL_RULES, Rule, SEVERITY_ORDER, lookup as _lookup  # noqa: F401

# Re-export every rule the engine still defines. Wrapped in try so a
# future per-cluster removal (e.g. `_rules/_path.py` deletion) doesn't
# break this import — `__getattr__` below covers the gap via lookup().
try:
    from ._rules import (  # noqa: F401
        EH001,
        FM001,
        FM002,
        FM003,
        FM004,
        FM005,
        FM006,
        FM007,
        FM008,
        FM009,
        I001,
        I002,
        I003,
        I004,
        I005,
        I006,
        I007,
        IO001,
        IO002,
        IO003,
        IO004,
        IO005,
        IO006,
        IO007,
        P001,
        P002,
        P003,
        P004,
        P005,
        PA001,
        PA002,
        PA003,
        PA004,
        PA005,
        S001,
        S002,
        S003,
        S004,
        S005,
        S006,
        S007,
        S008,
        ST001,
        ST002,
        ST003,
        ST004,
        ST005,
        ST006,
    )
except ImportError:
    pass


# PEP 562 — fall through to lookup() for any rule attribute the engine
# no longer defines. Plugin-shipped rules with the matching id get
# returned transparently; truly missing ids raise AttributeError so
# typos still surface.
_RULE_PREFIXES = ("S", "I", "IO", "PA", "ST", "EH", "P", "FM")


def __getattr__(name: str):
    if any(name.startswith(p) and name[len(p) :].isdigit() for p in _RULE_PREFIXES):
        rule = _lookup(f"STX-{name}")
        if rule is not None:
            return rule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
