"""Resolve installed skill providers and their operator enablement policy."""

from __future__ import annotations

from ..._core.config import _load_knob_state, load_config
from ...skill_registry import SkillRegistryError


class SkillPackages(dict):
    """Namespace targets with explicit owning distribution identities."""

    def __init__(self):
        super().__init__()
        self.owners: dict[str, str] = {}


def discover_skill_packages(*, package=None, owner=None, path=None) -> dict[str, str]:
    """Read skill entry points without importing their provider modules.

    One distribution may legitimately expose several skill namespaces. Duplicate
    namespace declarations by different owners or targets are refused.
    """
    from ..._core.provider_metadata import read_provider_metadata

    if owner is not None:
        from ..._core.names import normalize_distribution_name

        owner = normalize_distribution_name(owner)
    result = SkillPackages()
    enabled = _enabled_state()
    providers = read_provider_metadata("scitex_dev.skills", path=path)
    if owner is not None:
        providers = tuple(item for item in providers if item.distribution == owner)
    selected_owners = (
        {
            item.distribution
            for item in providers
            if package in (item.distribution, item.name)
        }
        if package is not None
        else None
    )
    for provider in providers:
        owner = provider.distribution
        if selected_owners is not None and owner not in selected_owners:
            continue
        if not enabled.get(owner, True):
            continue
        module = provider.target
        _validate_module_target(module)
        previous = result.get(provider.name)
        if previous is not None and (
            previous != module or result.owners[provider.name] != owner
        ):
            raise SkillRegistryError(
                f"ambiguous skill namespace {provider.name!r}: "
                f"{result.owners[provider.name]!r} and {owner!r}"
            )
        result[provider.name] = module
        result.owners[provider.name] = owner
    return result


def _enabled_state():
    enabled = {item.name: item.skills_enabled for item in load_config().packages}
    enabled.update(_load_knob_state().get("skills", {}))
    return enabled


def enabled_skill_packages(packages: dict[str, str]) -> dict[str, str]:
    """Apply config.yaml then the higher-precedence machine-managed knobs."""
    enabled = _enabled_state()
    result = SkillPackages()
    owners = getattr(packages, "owners", {})
    for name, module in packages.items():
        owner = owners.get(name, name)
        if enabled.get(owner, True):
            result[name] = module
            result.owners[name] = owner
    return result


def get_skill_package_root(owner: str, module: str):
    """Resolve an owner's resource tree from distribution metadata, never import it."""
    import json
    from importlib.metadata import distribution
    from pathlib import Path
    from urllib.parse import unquote, urlparse

    _validate_module_target(module)
    dist = distribution(owner)
    relative = Path(*module.split("."))
    direct = dist.read_text("direct_url.json")
    if direct:
        data = json.loads(direct)
        parsed = urlparse(data.get("url", ""))
        if (
            data.get("dir_info", {}).get("editable") is True
            and parsed.scheme == "file"
            and parsed.netloc in ("", "localhost")
        ):
            base = Path(unquote(parsed.path))
            for candidate in (base / "src" / relative, base / relative):
                if candidate.is_dir():
                    return candidate
    candidate = Path(dist.locate_file(relative))
    if candidate.is_dir():
        return candidate
    raise SkillRegistryError(
        f"skill provider {owner!r} has no metadata-resolvable module {module!r}"
    )


def _validate_module_target(module: str) -> None:
    """Skill resources accept dotted module identities, never factories or paths."""
    if not module or not all(part.isidentifier() for part in module.split(".")):
        raise SkillRegistryError(f"unsupported skill module target {module!r}")
