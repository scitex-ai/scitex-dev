"""Load owner-provided project-auditor rules and checks.

Providers in ``scitex_dev.audit.project`` expose ``get_plugin()`` returning
``{"rules": [(code, section, description, severity, slug)], "checks": [...]}``.
Each check accepts ``(repo_root, violation_class, violations)``. Providers
may also supply ``registry_checks`` accepting the explicit ``scitex_dir``
instead of a repository root. Registry checks run once in the host registry
auditor; they never scan a user's home during the per-project audit loop.
Providers must not import the project registry or Violation: both are assembled after
discovery, and the engine supplies the violation class when invoking checks.

The same validated bundle is used for registration and invocation. A broken
provider or duplicate declaration aborts discovery; dropping a declared
audit check would otherwise make a failing project appear compliant.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module, metadata
from typing import Any

_GROUP = "scitex_dev.audit.project"
_BUILTIN_VALUE = "scitex_dev._runtime_gitignore_plugin:get_plugin"


class ProjectPluginError(RuntimeError):
    """A declared project-auditor provider cannot safely be activated."""


@dataclass(frozen=True)
class _PluginBundle:
    rules: tuple[tuple[str, str, str, str, str], ...]
    checks: tuple[Callable, ...]
    registry_checks: tuple[Callable, ...] = ()


def _entry_points():
    """Read the group on both Python 3.9 and selectable metadata versions."""
    points = metadata.entry_points()
    if hasattr(points, "select"):
        return points.select(group=_GROUP)
    return points.get(_GROUP, ())


def _payload(provider: Callable, name: str) -> Mapping:
    try:
        if not callable(provider):
            raise TypeError("entry point must load a callable get_plugin")
        payload = provider()
        if not isinstance(payload, Mapping):
            raise TypeError("get_plugin must return a mapping")
        for key in ("rules", "checks"):
            if key not in payload or not isinstance(payload[key], (list, tuple)):
                raise TypeError(f"{key!r} must be a list or tuple")
        if "registry_checks" in payload and not isinstance(
            payload["registry_checks"], (list, tuple)
        ):
            raise TypeError("'registry_checks' must be a list or tuple")
        return payload
    except Exception as exc:
        raise ProjectPluginError(f"{_GROUP} provider {name!r}: {exc}") from exc


def _discover(points) -> _PluginBundle:
    rules: list[tuple[str, str, str, str, str]] = []
    checks: list[Callable] = []
    registry_checks: list[Callable] = []
    rule_owners: dict[str, str] = {}
    check_owners: dict[str, dict[tuple, str]] = {
        "checks": {},
        "registry_checks": {},
    }
    providers = []
    builtin_present = False
    for point in sorted(points, key=lambda ep: (ep.name, ep.value)):
        name = f"{point.name} ({point.value})"
        try:
            provider = point.load()
        except Exception as exc:
            raise ProjectPluginError(
                f"{_GROUP} provider {name!r} could not load: {exc}"
            ) from exc
        providers.append((name, provider))
        builtin_present |= point.value == _BUILTIN_VALUE
    if not builtin_present:
        # An editable/source checkout may have older installed metadata. Use
        # the same owner provider, never a second copy of its rule/check logic.
        try:
            provider = import_module("scitex_dev._runtime_gitignore_plugin").get_plugin
        except Exception as exc:
            raise ProjectPluginError(
                f"{_GROUP} built-in provider {_BUILTIN_VALUE!r} could not load: {exc}"
            ) from exc
        providers.append((_BUILTIN_VALUE, provider))
    for name, provider in providers:
        payload = _payload(provider, name)
        for rule in payload["rules"]:
            if (
                not isinstance(rule, tuple)
                or len(rule) != 5
                or not all(isinstance(field, str) for field in rule)
                or not all(field.strip() for field in rule[:3])
                or rule[3] not in {"E", "W", "I"}
            ):
                raise ProjectPluginError(
                    f"{_GROUP} provider {name!r}: invalid five-field rule {rule!r}"
                )
            code = rule[0]
            if code in rule_owners:
                raise ProjectPluginError(
                    f"{_GROUP}: duplicate rule {code!r} from {name!r}; "
                    f"already declared by {rule_owners[code]!r}"
                )
            rule_owners[code] = name
            rules.append(rule)
        for scope, destination in (
            ("checks", checks),
            ("registry_checks", registry_checks),
        ):
            owners = check_owners[scope]
            for check in payload.get(scope, ()):
                if not callable(check):
                    raise ProjectPluginError(
                        f"{_GROUP} provider {name!r}: {scope} check {check!r} "
                        "must be callable"
                    )
                module = getattr(check, "__module__", None)
                qualname = getattr(check, "__qualname__", None)
                identity = (module, qualname) if module and qualname else (id(check),)
                if identity in owners:
                    raise ProjectPluginError(
                        f"{_GROUP}: duplicate check {check!r} in {scope!r} from {name!r}; "
                        f"already declared by {owners[identity]!r}"
                    )
                owners[identity] = name
                destination.append(check)
    return _PluginBundle(tuple(rules), tuple(checks), tuple(registry_checks))


@lru_cache(maxsize=1)
def _installed_plugins() -> _PluginBundle:
    return _discover(_entry_points())


def load_plugins(*, entry_points_iter: Callable | None = None) -> _PluginBundle:
    """Return validated rules/checks, caching normal installed discovery.

    ``entry_points_iter`` supplies real entry-point objects for an isolated
    test or embedding host. Injected discovery bypasses the process cache.
    The owner's mandatory rule is present even when metadata predates it.
    """
    if entry_points_iter is not None:
        return _discover(entry_points_iter())
    return _installed_plugins()


def register_plugin_rules(
    registry: MutableMapping,
    rule_class: Callable,
    *,
    plugins: _PluginBundle | None = None,
) -> None:
    """Merge rules atomically, refusing collisions with engine-owned IDs."""
    plugins = load_plugins() if plugins is None else plugins
    collisions = set(registry).intersection(rule[0] for rule in plugins.rules)
    if collisions:
        raise ProjectPluginError(
            f"{_GROUP}: rules already registered by the engine: {sorted(collisions)!r}"
        )
    additions: dict[str, Any] = {rule[0]: rule_class(*rule) for rule in plugins.rules}
    registry.update(additions)


__all__ = ["ProjectPluginError", "load_plugins", "register_plugin_rules"]
