"""Discover and load linter rule plugins via entry points."""

import logging
import sys

_logger = logging.getLogger(__name__)
_cache = None


def _iter_entry_points(group):
    """Yield entry points, compatible with Python 3.9+."""
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        return entry_points(group=group)
    else:
        from importlib.metadata import entry_points

        eps = entry_points()
        return eps.get(group, [])


def load_plugins():
    """Load all registered linter plugins. Cached after first call.

    Returns dict with keys: rules, call_rules, axes_hints, checkers.

    Pillar-0 instrumentation (#TBD): after the entry-point scan we hand
    the list of successfully-loaded plugin payloads to
    :mod:`scitex_dev.linter._health` so it can emit an L1 stderr notice
    if no IO/PA category rules registered AND scitex-io is missing.
    That makes the silent-skip path visible to the agent feedback
    surface (run_lint.sh hook) instead of going quiet.
    """
    global _cache
    if _cache is not None:
        return _cache

    merged = {
        "rules": {},
        "call_rules": {},
        "axes_hints": {},
        "checkers": [],
    }
    plugin_payloads: list = []

    # Canonical entry-point group. The legacy `scitex_linter.plugins`
    # group is no longer read — all leaf packages now register under
    # the new name (the dual-registration window has closed).
    for ep in _iter_entry_points("scitex_dev.linter.plugins"):
        try:
            get_plugin = ep.load()
            plugin = get_plugin()
        except Exception:
            _logger.debug("Failed to load linter plugin %s", ep.name, exc_info=True)
            continue

        plugin_payloads.append(plugin)
        for rule in plugin.get("rules", []):
            merged["rules"][rule.id] = rule
        merged["call_rules"].update(plugin.get("call_rules", {}))
        merged["axes_hints"].update(plugin.get("axes_hints", {}))
        merged["checkers"].extend(plugin.get("checkers", []))

    # Fail-loud — emits L1 notice on stderr if no IO/PA plugins registered
    # and scitex-io is absent from the env. See _health.record_plugin_load
    # for the exact predicate and the SCITEX_DEV_LINTER_QUIET escape.
    try:
        from . import _health as _h

        _h.record_plugin_load(plugin_payloads)
    except Exception:  # pragma: no cover - health module must NEVER break loading
        _logger.debug("plugin-load health record failed", exc_info=True)

    _cache = merged
    return _cache


def reset():
    """Reset cache (for testing).

    Also resets :mod:`scitex_dev.linter._health` state so a test can
    re-trigger the L1/L2 notices in the same process. Production callers
    never invoke this — the cache is process-lifetime by design.
    """
    global _cache
    _cache = None
    try:
        from . import _health as _h

        _h.reset()
    except Exception:  # pragma: no cover
        pass
