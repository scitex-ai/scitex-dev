"""Installed hierarchy declarations, without loading providers or SDK code."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from .._core.names import normalize_distribution_name
from .._core.provider_metadata import ProviderMetadata, read_provider_metadata

HierarchyProvider = ProviderMetadata

__all__ = ["HierarchyProvider", "list_hierarchy_providers"]

_TARGET = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z",
    re.ASCII,
)


def list_hierarchy_providers(
    *, package: str | None = None, path: Sequence[str | Path] | None = None
) -> tuple[HierarchyProvider, ...]:
    """Read and validate the installed ``scitex_dev.hierarchy`` declarations.

    Each canonical owning distribution declares exactly one equally named
    ``module:attribute`` target. Ambiguity or malformed declarations fail before
    optional package filtering. No target is imported or certified callable.
    Missing versions remain unknown. An empty catalog does not imply a tree.
    ``path`` restricts metadata discovery; no registry fallback is consulted.
    """
    selected = normalize_distribution_name(package) if package is not None else None
    rows = read_provider_metadata("scitex_dev.hierarchy", path=path)
    seen: set[str] = set()
    for row in rows:
        if row.name != row.distribution:
            raise ValueError(
                f"hierarchy provider name must equal its canonical owner: {row.distribution}"
            )
        if row.distribution in seen:
            raise ValueError(f"duplicate hierarchy provider: {row.distribution}")
        seen.add(row.distribution)
        if _TARGET.fullmatch(row.target) is None:
            raise ValueError(
                f"hierarchy provider needs module:attribute: {row.distribution}"
            )
    return tuple(
        row for row in rows if selected is None or row.distribution == selected
    )
