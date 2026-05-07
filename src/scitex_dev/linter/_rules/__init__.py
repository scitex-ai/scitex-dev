"""Rule definitions for SciTeX linter.

Re-exports all rules from category sub-modules for backward compatibility.
Also exposes `lookup(rule_id)` — the merged engine+plugin rule resolver
used during the per-package rule migration (engine duplicates removed
one cluster at a time; `lookup()` falls through to plugin-shipped rules).
"""

from ._base import Rule
from ._lookup import lookup, reset as reset_lookup_cache  # noqa: F401
from ._error_handling import EH001
from ._figure import FM001, FM002, FM003, FM004, FM005, FM006, FM007, FM008, FM009
from ._imports import I001, I002, I003, I004, I005, I006, I007
from ._io import IO001, IO002, IO003, IO004, IO005, IO006, IO007

# PA001-PA005 migrated to scitex-io plugin (see ./_lookup.py); engine
# falls through to that via lookup() for any rules.PA* resolution.
from ._plot import P001, P002, P003, P004, P005
from ._stats import ST001, ST002, ST003, ST004, ST005, ST006
from ._structure import S001, S002, S003, S004, S005, S006, S007, S008

ALL_RULES = {
    r.id: r
    for r in [
        EH001,
        S001,
        S002,
        S003,
        S004,
        S005,
        S006,
        S007,
        S008,
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
        ST001,
        ST002,
        ST003,
        ST004,
        ST005,
        ST006,
        FM001,
        FM002,
        FM003,
        FM004,
        FM005,
        FM006,
        FM007,
        FM008,
        FM009,
    ]
}

SEVERITY_ORDER = {"error": 2, "warning": 1, "info": 0}

__all__ = [
    "Rule",
    "ALL_RULES",
    "SEVERITY_ORDER",
    "lookup",
    "reset_lookup_cache",
    "EH001",
    "S001",
    "S002",
    "S003",
    "S004",
    "S005",
    "S006",
    "S007",
    "S008",
    "I001",
    "I002",
    "I003",
    "I004",
    "I005",
    "I006",
    "I007",
    "IO001",
    "IO002",
    "IO003",
    "IO004",
    "IO005",
    "IO006",
    "IO007",
    "P001",
    "P002",
    "P003",
    "P004",
    "P005",
    "ST001",
    "ST002",
    "ST003",
    "ST004",
    "ST005",
    "ST006",
    "FM001",
    "FM002",
    "FM003",
    "FM004",
    "FM005",
    "FM006",
    "FM007",
    "FM008",
    "FM009",
]
