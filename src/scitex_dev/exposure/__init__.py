"""Immutable operator preferences, separate from installed capability metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .._core.names import normalize_distribution_name

__all__ = ["ExposurePolicy", "ExposurePreference", "load_exposure_policy"]
_FIELDS = {"cli": "cli_enabled", "mcp": "mcp_enabled", "skills": "skills_enabled"}


def _field(surface: str) -> str:
    if surface not in _FIELDS:
        raise ValueError("surface must be cli, mcp or skills")
    return _FIELDS[surface]


@dataclass(frozen=True)
class ExposurePreference:
    """One configured owner, not proof of an installed or callable provider."""

    distribution: str
    cli_enabled: bool = True
    mcp_enabled: bool = True
    skills_enabled: bool = True

    def is_enabled(self, surface: str) -> bool:
        """Return this owner's independent preference for a supported surface."""
        return getattr(self, _field(surface))


@dataclass(frozen=True)
class ExposurePolicy:
    """A construction-time snapshot; unconfigured owners retain default True.

    This controls aggregation/mounting, not standalone executables or imports.
    Enabled does not create capabilities or override invalid/none/ambiguous
    declarations, host retirement policy, authorization or Web admission.
    """

    preferences: tuple[ExposurePreference, ...] = ()
    config_path: Path | None = None
    knob_state_path: Path | None = None

    def is_enabled(self, distribution: str, surface: str) -> bool:
        """Resolve any canonical owner, including unregistered installed leaves."""
        name = normalize_distribution_name(distribution)
        _field(surface)
        for row in self.preferences:
            if row.distribution == name:
                return row.is_enabled(surface)
        return True


def load_exposure_policy(
    config_path: str | Path | None = None,
    *,
    knob_state_path: str | Path | None = None,
) -> ExposurePolicy:
    """Resolve one immutable config/state snapshot without loading any provider.

    Reuses Dev's existing file selection/defaults/YAML/override precedence.
    Malformed state and conflicting owner identities refuse visibly. Raw state
    overrides also apply to owners absent from the curated package defaults.
    No file is created and no package inventory is discovered by this helper.
    """
    import yaml

    from .._core._knobs import (
        _canonical_surface_state,
        _knob_state_path,
        _load_knob_state,
    )
    from .._core.config import _load_config, get_config_path

    config_file = (
        Path(config_path).expanduser().absolute()
        if config_path is not None
        else get_config_path().absolute()
    )
    state_file = (
        Path(knob_state_path).expanduser().absolute()
        if knob_state_path is not None
        else _knob_state_path().absolute()
    )
    state = _canonical_surface_state(_load_knob_state(state_file, strict=True))
    try:
        config = _load_config(config_file, state, strict=True)
    except (AttributeError, KeyError, OSError, yaml.YAMLError) as exc:
        raise ValueError("invalid exposure package configuration") from exc
    owners = {}
    for package in config.packages:
        owner = normalize_distribution_name(package.pypi_name or package.name)
        values = {field: getattr(package, field) for field in _FIELDS.values()}
        for kind, field in _FIELDS.items():
            if owner in state[kind]:
                values[field] = state[kind][owner]
        row = ExposurePreference(owner, **values)
        if owner in owners and owners[owner] != row:
            raise ValueError("conflicting canonical package preferences")
        owners[owner] = row
    for kind, field in _FIELDS.items():
        for owner, value in state[kind].items():
            if owner not in owners:
                owners[owner] = ExposurePreference(owner)
            owners[owner] = replace(owners[owner], **{field: value})
    return ExposurePolicy(
        tuple(owners[name] for name in sorted(owners)), config_file, state_file
    )
