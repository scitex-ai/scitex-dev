"""Shared installed declaration reader: metadata only, never entry-point loading."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Sequence

from .names import normalize_distribution_name

__all__ = ["ProviderMetadata", "read_provider_metadata"]


@dataclass(frozen=True)
class ProviderMetadata:
    """Leaf ownership and target, without import side effects or host paths."""

    name: str
    target: str
    distribution: str
    version: str | None
    summary: str


def read_provider_metadata(
    group: str, *, path: Sequence[str | Path] | None = None
) -> tuple[ProviderMetadata, ...]:
    """Read a declared provider group, preserving duplicate ownership claims.

    No registry fallback is added. This is installed declaration metadata,
    not an enablement decision, source import or live availability check.
    """
    distributions = (
        metadata.distributions(path=[str(item) for item in path])
        if path is not None else metadata.distributions()
    )
    rows: list[ProviderMetadata] = []
    for distribution in distributions:
        declarations = [point for point in distribution.entry_points if point.group == group]
        if not declarations:
            continue
        info = distribution.metadata
        owner = info.get("Name")
        if not owner:
            raise ValueError("provider distribution lacks Name metadata")
        owner = normalize_distribution_name(owner)
        for point in declarations:
            rows.append(ProviderMetadata(
                name=point.name, target=point.value, distribution=owner,
                version=info.get("Version") or None, summary=info.get("Summary") or "",
            ))
    return tuple(sorted(rows, key=lambda row: (
        row.name, row.distribution, row.target, row.version or "", row.summary
    )))
