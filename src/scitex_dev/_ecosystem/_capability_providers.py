"""Internal capability-provider declarations from installed distribution metadata.

Reading or selecting a row does not import/enable its target, certify module
ownership or behavior, or change exposure/audit policy. The shared metadata
reader owns discovery; this module defines the new declaration group's shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .._core.names import normalize_distribution_name
from .._core.provider_metadata import ProviderMetadata, read_provider_metadata

_GROUP = "scitex_dev.capabilities"


def read_capability_providers(
    *, path: Sequence[str | Path] | None = None,
) -> tuple[ProviderMetadata, ...]:
    """Read inert factory declarations, preserving every ownership claim.

    Targets must use module:attribute syntax. Syntactic validity does not prove
    that either exists or is callable. Missing versions remain unknown.
    """
    rows = read_provider_metadata(_GROUP, path=path)
    for row in rows:
        if not row.name.strip() or row.name != row.name.strip():
            raise ValueError("capability provider name must be nonempty and unpadded")
        module, separator, attribute = row.target.partition(":")
        parts = module.split(".") + attribute.split(".")
        if not separator or not all(part.isidentifier() for part in parts):
            raise ValueError(
                f"capability provider target must be module:attribute: {row.target!r}"
            )
    return rows


def select_capability_provider(
    rows: Sequence[ProviderMetadata], *, distribution: str, name: str,
) -> ProviderMetadata:
    """Select exactly one declaration by canonical owner and exact provider name.

    Never fall back to another owner's namespace or collapse duplicate rows,
    even if their targets and versions agree. This checks declaration identity;
    target ownership, enablement and live availability require separate checks.
    """
    owner = normalize_distribution_name(distribution)
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError("provider name must be nonempty and unpadded")
    if any(not isinstance(row, ProviderMetadata) for row in rows):
        raise TypeError("rows must contain ProviderMetadata")
    matches = tuple(row for row in rows if row.distribution == owner and row.name == name)
    if not matches:
        raise LookupError(f"no capability provider {name!r} declared by {owner!r}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous capability provider {name!r} for {owner!r}")
    return matches[0]
