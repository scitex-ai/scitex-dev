"""Engine-side lookup constants for the SciTeX checker.

The engine ships NO call->rule or axes-hint mappings. Those tables are owned
by the leaf plugins whose API the rules enforce and arrive through
``load_plugins()`` (``call_rules`` / ``call_rule_groups`` / ``axes_hints``):

- ``STX-IO*`` / ``STX-PA*``  -> scitex-io
- ``STX-ST*``                -> scitex-stats
- ``STX-P*`` / ``STX-FM*``   -> figrecipe

The engine used to carry a duplicate ``_CALL_RULES_SPEC`` / ``_AXES_HINTS_SPEC``
(a strict subset of the plugins' tables). It added no coverage, and its
hyphenated ``STX-PA-003`` / ``STX-PA-004`` ids never resolved, so those rows
were silently dropped. Removed rather than repaired: one owner per mapping.

``PRINT_RULE`` stays lazy (PEP 562 ``__getattr__``): first access triggers
``lookup()`` through the plugin loader, which is unsafe at import time because
leaf plugins import from ``scitex_dev.linter.checker``.
"""

from __future__ import annotations

from . import rules  # noqa: F401  (kept for legacy attribute access)

# Names that refer to the scitex package (skip linting on these)
STX_NAMES = frozenset(("stx", "scitex", "scitex_io"))

# Modules to skip for axes hints
AXES_SKIP = frozenset(
    (
        "stx",
        "scitex",
        "os",
        "sys",
        "Path",
        "math",
        "np",
        "numpy",
        "pd",
        "pandas",
    )
)


# One-time lazy cache. Reset via `_reset_caches()` in tests.
_PRINT_RULE_CACHE = None


def _reset_caches() -> None:
    """Drop lazy caches (for tests that swap plugins at runtime)."""
    global _PRINT_RULE_CACHE
    _PRINT_RULE_CACHE = None


def __getattr__(name):
    """Lazy-resolve PRINT_RULE (PEP 562)."""
    global _PRINT_RULE_CACHE
    if name == "PRINT_RULE":
        if _PRINT_RULE_CACHE is None:
            from ._rules import lookup

            _PRINT_RULE_CACHE = lookup("STX-P005")
        return _PRINT_RULE_CACHE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
