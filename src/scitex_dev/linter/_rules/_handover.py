"""Engine rules handed over to the leaf package whose API they enforce.

Lint rules belong to their owning package (``08_linter-plugins.md``;
ownership table: ``docs/rule-ownership.md``). A rule that started life in
the engine moves WITHOUT a behaviour change in two steps:

1. **Handover (this table).** The owning leaf's plugin declares the rule —
   same id, severity, category, message, suggestion, ``requires``, scope —
   and ships the checker that emits it. When that provider is installed, the
   engine yields: the loader accepts the leaf's declaration instead of
   rejecting it as a collision, and ``SciTeXChecker`` stops emitting the id.
   When the provider is NOT installed (an older leaf, or a lean env), the
   engine keeps emitting it exactly as before. That is the compatibility
   shim: the effective rule set and findings are identical either way.

2. **Removal (later).** Once the leaf release that ships the rule is on PyPI
   and pinned where the rule must fire, delete the engine definition, its
   emission, and the row below. The leaf's declaration then stands alone.

Only the provider distribution NAMED here may take an id over; any other
plugin declaring an engine id still fails loading as a collision, so a
handover can never be claimed by accident.

The same table moves an id between two PLUGINS (``STX-P005``: declared by
figrecipe, emitted by the engine, owned by scitex-session). While both
declare it, the named owner's declaration wins and the other is dropped
instead of failing as a duplicate, so the predecessor can keep declaring the
id until the owner's release is pinned — no mixed-version install ever loses
the rule.
"""

from __future__ import annotations

from types import MappingProxyType

__all__ = ["HANDOVER", "handover_owner"]

# rule id -> distribution that owns it (PEP 503-normalized).
HANDOVER = MappingProxyType(
    {
        # The @stx.session decorator contract — scitex-session's API.
        "STX-S001": "scitex-session",  # main() lacks @stx.session/@stx.module
        "STX-S003": "scitex-session",  # argparse in a session script
        "STX-S004": "scitex-session",  # session function must return an int
        "STX-S006": "scitex-session",  # INJECTED parameters undeclared
        # config/*.yaml -> injected CONFIG (detector ported verbatim).
        "STX-S008": "scitex-session",  # hard-coded analysis parameter
        # Session injection contract — what @stx.session hands the function.
        "STX-I006": "scitex-session",  # `import random` -> injected rngg
        "STX-P010": "scitex-session",  # top-level figrecipe -> injected plt
        "STX-P005": "scitex-session",  # print() in a session -> logger
        # Raw library import where the owning SciTeX package is the API.
        "STX-I001": "figrecipe",  # matplotlib.pyplot -> stx.plt
        "STX-I009": "figrecipe",  # seaborn -> stx.plt
        "STX-I002": "scitex-stats",  # scipy.stats -> stx.stats
        "STX-I003": "scitex-io",  # pickle -> stx.io
        "STX-I007": "scitex-logging",  # stdlib logging -> scitex-logging
        # scitex-io's load_configs() API.
        "STX-S007": "scitex-io",  # load_configs() result not UPPER_CASE
    }
)


def handover_owner(rule_id: str):
    """Return the distribution that owns *rule_id*, or None if not handed over."""
    return HANDOVER.get(rule_id)


# EOF
