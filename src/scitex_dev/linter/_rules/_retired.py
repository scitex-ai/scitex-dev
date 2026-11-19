"""Retired rule ids: no longer active, kept reserved.

A retired id never fires and is not listed as an active rule, but it stays
RESERVED: no plugin may declare it (that would silently give an old id a new
meaning), its ``Rule`` object stays importable for back-compat
(``from scitex_dev.linter.rules import I004``), and a project config that
still names it gets a ``DeprecationWarning`` pointing at the successor.

- ``STX-I004`` / ``STX-I005`` were declared but had no emitter since the
  per-package migration; scitex-io's call rules (pandas I/O -> ``STX-IO003``
  / ``STX-IO004``; numpy save/load -> ``STX-IO001`` / ``STX-IO002``) cover
  what they described. Retiring them changes no finding.
"""

from __future__ import annotations

import warnings
from types import MappingProxyType

__all__ = ["RETIRED", "warn_retired_config"]

# retired id -> the rule(s) that cover its concern now
RETIRED = MappingProxyType(
    {
        "STX-I004": ("STX-IO003", "STX-IO004"),
        "STX-I005": ("STX-IO001", "STX-IO002"),
    }
)


def warn_retired_config(config) -> None:
    """Warn when *config* disables or re-severities a retired id."""
    named = set(getattr(config, "disable", ()) or ()) | set(
        getattr(config, "per_rule_severity", {}) or {}
    )
    for rule_id in sorted(named & set(RETIRED)):
        successors = " / ".join(RETIRED[rule_id])
        warnings.warn(
            f"{rule_id} is retired (it never fired); its concern is covered by "
            f"{successors}. Remove it from the linter config.",
            DeprecationWarning,
            stacklevel=3,
        )


# EOF
