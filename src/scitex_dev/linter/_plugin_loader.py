"""Discover validated linter providers without dropping declared coverage."""

from collections.abc import Mapping
import os
import sys

import scitex_logging as slogging

_logger = slogging.getLogger(__name__)
_cache = None
_GROUP = "scitex_dev.linter.plugins"
_LOGGING_VALUE = "scitex_logging._linter_plugin:get_plugin"


class LinterPluginError(RuntimeError):
    """A provider cannot safely contribute its declared linter coverage."""


def _quiet() -> bool:
    """Return True when the fail-loud plugin-load notice is suppressed.

    Mirrors :func:`scitex_dev.linter._health._quiet` — both the
    documented ``SCITEX_DEV_LINTER_QUIET`` switch and the legacy
    ``SCITEX_DEV_NO_AUDIT_DISCLAIMER`` (used by ``audit-all`` to silence
    sub-process noise) silence the notice. An empty string / ``0`` /
    ``false`` does NOT silence.
    """
    for env in ("SCITEX_DEV_LINTER_QUIET", "SCITEX_DEV_NO_AUDIT_DISCLAIMER"):
        val = os.environ.get(env, "")
        if val and val not in ("0", "false", "False", ""):
            return True
    return False


def _remediation_hint(ep_name: str, exc: Exception) -> str:
    """Return an ACTIONABLE next-step for a plugin that failed to load.

    A plugin advertised via the ``scitex_dev.linter.plugins`` entry-point
    group but unimportable is almost always one of two cases, each with a
    different fix:

    * **Stale build / vestigial entry point.** The distribution declares
      an entry point pointing at a module the *installed* build no longer
      ships (``No module named '<pkg>._linter_plugin'``). The umbrella
      ``scitex`` package is the canonical example — it dropped
      ``scitex._linter_plugin`` in the umbrella-thinning refactor, so an
      env carrying an OLDER ``scitex`` wheel still advertises the entry
      point while the module is gone (neurovista symptom 2026-06-14). Fix:
      upgrade/reinstall that distribution so its metadata and code agree.

    * **Broken plugin module.** The module exists but raises on import
      (e.g. a circular import — figrecipe's figure-style checkers hit this
      for months). Fix: repair the plugin's import path.
    """
    if isinstance(exc, ModuleNotFoundError):
        missing = getattr(exc, "name", "") or str(exc)
        # `<pkg>._linter_plugin` missing → the entry point outlived the
        # module it points at. Name the distribution + the reinstall fix.
        if "._linter_plugin" in missing:
            dist = missing.split(".", 1)[0] or ep_name
            return (
                f"the {ep_name!r} plugin advertises module {missing!r} "
                f"which this build does NOT ship — the entry point is "
                f"STALE (the installed {dist!r} wheel is older than its "
                f"declared metadata). FIX: `pip install -U "
                f"--force-reinstall --no-deps {dist}` so its entry points "
                f"match the shipped modules. If {dist!r} intentionally no "
                f"longer provides linter rules, the stale wheel is the only "
                f"thing keeping this dead entry point alive."
            )
    # Generic import failure (circular import, ImportError, …).
    return (
        f"the {ep_name!r} plugin module raised on import — its rules / "
        f"checkers are NOT active. FIX: import `{ep_name}` (or its "
        f"`_linter_plugin`) directly and resolve the error above "
        f"(commonly a circular import)."
    )


def _iter_entry_points(group):
    """Yield entry points, compatible with Python 3.9+."""
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points

        return entry_points(group=group)
    else:
        from importlib.metadata import distributions

        # Python 3.9's flattened entry_points() result loses distribution
        # ownership. Keep it explicitly when proving replacement contracts.
        return [
            _OwnedEntryPoint(point, distribution)
            for distribution in distributions()
            for point in distribution.entry_points
            if point.group == group
        ]


class _OwnedEntryPoint:
    """Retain actual distribution ownership on Python 3.9 entry points."""

    def __init__(self, point, distribution):
        self._point = point
        self.dist = distribution

    def __getattr__(self, name):
        return getattr(self._point, name)


def _validate_payload(plugin, name):
    if not isinstance(plugin, Mapping):
        raise LinterPluginError(
            f"{_GROUP} provider {name!r}: payload must be a mapping"
        )
    for key in ("rules", "checkers"):
        if key in plugin and not isinstance(plugin[key], (list, tuple)):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: {key} must be a list or tuple"
            )
    for key in ("call_rules", "axes_hints"):
        if key in plugin and not isinstance(plugin[key], Mapping):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: {key} must be a mapping"
            )
    seen_rule_ids = set()
    for rule in plugin.get("rules", ()):
        if (
            not isinstance(getattr(rule, "id", None), str)
            or not rule.id.strip()
            or not isinstance(getattr(rule, "severity", None), str)
            or rule.severity not in {"error", "warning", "info"}
            or not isinstance(getattr(rule, "category", None), str)
            or not isinstance(getattr(rule, "message", None), str)
            or not isinstance(getattr(rule, "suggestion", None), str)
            or not isinstance(getattr(rule, "requires", None), str)
        ):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: invalid Rule {rule!r}"
            )
        if rule.id in seen_rule_ids:
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: duplicate rule {rule.id!r}"
            )
        seen_rule_ids.add(rule.id)
    for key, rule in plugin.get("call_rules", {}).items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not all(value is None or isinstance(value, str) for value in key)
            or not isinstance(getattr(rule, "id", None), str)
        ):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: invalid call rule {key!r}"
            )
    for key, rule in plugin.get("axes_hints", {}).items():
        if not isinstance(key, str) or not isinstance(getattr(rule, "id", None), str):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: invalid axes hint {key!r}"
            )
    own_rules = {rule.id: rule for rule in plugin.get("rules", ())}
    for rule in (
        *plugin.get("call_rules", {}).values(),
        *plugin.get("axes_hints", {}).values(),
    ):
        if rule.id in own_rules and own_rules[rule.id] != rule:
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: mapping references contradictory rule {rule.id!r}"
            )
    seen_checkers = set()
    for checker in plugin.get("checkers", ()):
        if not callable(checker):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: checker must be callable"
            )
        if id(checker) in seen_checkers:
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: duplicate checker {checker!r}"
            )
        seen_checkers.add(id(checker))


def load_plugins(*, entry_points_iter=None):
    """Load rule providers, requiring the installed logging owner.

    The four existing payload keys and opt-in figure gating remain unchanged.
    Declared providers cannot silently disappear: import, schema, ownership,
    and duplicate failures abort loading regardless of diagnostic verbosity.
    Injected entry points bypass the process cache and use the same validation.
    """
    global _cache
    injected = entry_points_iter is not None
    if _cache is not None and not injected:
        return _cache
    merged = {
        "rules": {},
        "call_rules": {},
        "axes_hints": {},
        "checkers": [],
        "call_rule_groups": {},
        "provider_replacements": (),
    }
    owners = {"rules": {}, "call_rules": {}, "axes_hints": {}, "checkers": {}}
    provider_owners = {}
    plugin_payloads = []
    logging_present = False
    providers = []
    points = entry_points_iter() if injected else _iter_entry_points(_GROUP)
    for ep in sorted(
        points, key=lambda point: (point.name, getattr(point, "value", ""))
    ):
        value = getattr(ep, "value", None)
        name = f"{ep.name} ({value})"
        if value is not None and value in provider_owners:
            raise LinterPluginError(
                f"{_GROUP}: duplicate provider {name!r}; already declared by {provider_owners[value]!r}"
            )
        if value is not None:
            provider_owners[value] = name
        try:
            factory = ep.load()
            if not callable(factory):
                raise TypeError("entry point must load a callable get_plugin")
            plugin = factory()
        except Exception as exc:
            raise LinterPluginError(
                f"{_GROUP} provider {name!r} could not load: {type(exc).__name__}: {exc}"
            ) from exc
        _validate_payload(plugin, name)
        is_logging = ep.name == "scitex-logging" and value == _LOGGING_VALUE
        logging_present |= is_logging
        if is_logging and (
            not any(
                rule.id == "PS-220" and rule.severity == "error"
                for rule in plugin.get("rules", ())
            )
            or not any(
                getattr(checker, "mandatory", False)
                and getattr(checker, "accepts_filepath", False)
                for checker in plugin.get("checkers", ())
            )
        ):
            raise LinterPluginError(
                f"{_GROUP} provider {name!r}: mandatory PS-220 error rule and filepath-aware checker are required"
            )
        providers.append((ep, plugin, is_logging, name))
    from ._provider_replacements import ProviderReplacementError, resolve_replacements

    try:
        providers, receipts = resolve_replacements(providers)
    except ProviderReplacementError as exc:
        raise LinterPluginError(f"{_GROUP}: {exc}") from exc
    merged["provider_replacements"] = receipts
    for ep, plugin, is_logging, name in providers:
        for rule in plugin.get("rules", ()):
            if rule.id == "PS-220" and not is_logging:
                raise LinterPluginError(
                    f"{_GROUP}: PS-220 belongs to scitex-logging, not {name!r}"
                )
            if rule.id in owners["rules"]:
                raise LinterPluginError(
                    f"{_GROUP}: duplicate rule {rule.id!r} from {name!r}; already declared by {owners['rules'][rule.id]!r}"
                )
            owners["rules"][rule.id] = name
            merged["rules"][rule.id] = rule
        for key in ("call_rules", "axes_hints"):
            for identifier, rule in plugin.get(key, {}).items():
                if key == "call_rules":
                    group = merged["call_rule_groups"].setdefault(identifier, [])
                    if any(existing.id == rule.id for existing in group):
                        raise LinterPluginError(
                            f"{_GROUP}: duplicate call rule {rule.id!r} for {identifier!r} from {name!r}"
                        )
                    # Independent concerns can inspect the same API pattern.
                    # Preserve the first provider's single-Rule view for old
                    # consumers and expose every distinct owner to the engine.
                    group.append(rule)
                    merged["call_rules"].setdefault(identifier, rule)
                    owners[key].setdefault(identifier, name)
                    continue
                if identifier in owners[key]:
                    raise LinterPluginError(
                        f"{_GROUP}: duplicate {key} {identifier!r} from {name!r}; already declared by {owners[key][identifier]!r}"
                    )
                owners[key][identifier] = name
                merged[key][identifier] = rule
        for checker in plugin.get("checkers", ()):
            module = getattr(checker, "__module__", None)
            qualname = getattr(checker, "__qualname__", None)
            # Factories may produce several independently bound classes with
            # the same lexical <locals> name (figrecipe does this). Those are
            # distinct checkers; repeating the same object is still rejected.
            identity = (
                (module, qualname)
                if module and qualname and "<locals>" not in qualname
                else (id(checker),)
            )
            if identity in owners["checkers"]:
                raise LinterPluginError(
                    f"{_GROUP}: duplicate checker {identity!r} from {name!r}; already declared by {owners['checkers'][identity]!r}"
                )
            owners["checkers"][identity] = name
            merged["checkers"].append(checker)
        plugin_payloads.append(plugin)
    if not logging_present:
        raise LinterPluginError(
            f"{_GROUP}: mandatory scitex-logging provider {_LOGGING_VALUE!r} is absent. "
            "Install matching scitex-logging and scitex-dev builds that declare the logging linter entry point; "
            "linting cannot report success without PS-220 coverage."
        )
    from ._rules import ALL_RULES

    collisions = set(ALL_RULES).intersection(merged["rules"])
    if collisions:
        raise LinterPluginError(
            f"{_GROUP}: rules already registered by the engine: {sorted(collisions)!r}"
        )
    declared_rules = {**ALL_RULES, **merged["rules"]}
    referenced = [
        rule for group in merged["call_rule_groups"].values() for rule in group
    ] + list(merged["axes_hints"].values())
    for rule in referenced:
        if declared_rules.get(rule.id) != rule:
            raise LinterPluginError(
                f"{_GROUP}: call/axes mapping references undeclared or contradictory rule {rule.id!r}"
            )
    merged["call_rule_groups"] = {
        key: tuple(group) for key, group in merged["call_rule_groups"].items()
    }
    if not _quiet():
        for receipt in receipts:
            _logger.info(
                "linter: %s (%s) replaces %s (%s) for rules %s",
                receipt["successor_distribution"],
                receipt["successor_entry_point"],
                receipt["predecessor_distribution"],
                receipt["predecessor_entry_point"],
                ", ".join(receipt["rule_ids"]),
            )
    if injected:
        return merged
    try:
        from . import _health

        _health.record_plugin_load(plugin_payloads)
    except Exception:
        _logger.debug("plugin-load health record failed", exc_info=True)
    _cache = merged
    return merged


def reset():
    """Drop the process cache and health tally for isolated tests."""
    global _cache
    _cache = None
    try:
        from . import _health

        _health.reset()
    except Exception:
        pass
