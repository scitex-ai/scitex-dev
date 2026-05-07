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

    Returns dict with keys: rules, call_rules, axes_hints, checkers
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

    # Read both the legacy and the canonical entry-point groups so leaf
    # packages can migrate at their own pace. Same plugin registered under
    # both groups is deduplicated by entry-point name.
    seen_names: set = set()
    for group in ("scitex_dev.linter.plugins", "scitex_linter.plugins"):
        for ep in _iter_entry_points(group):
            key = (group, ep.name)
            if ep.name in seen_names:
                continue
            seen_names.add(ep.name)
            try:
                get_plugin = ep.load()
                plugin = get_plugin()
            except Exception:
                _logger.debug(
                    "Failed to load linter plugin %s (%s)", ep.name, key, exc_info=True
                )
                continue

            for rule in plugin.get("rules", []):
                merged["rules"][rule.id] = rule
            merged["call_rules"].update(plugin.get("call_rules", {}))
            merged["axes_hints"].update(plugin.get("axes_hints", {}))
            merged["checkers"].extend(plugin.get("checkers", []))

    _cache = merged
    return _cache


def reset():
    """Reset cache (for testing)."""
    global _cache
    _cache = None
