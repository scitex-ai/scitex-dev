"""Inert installed documentation-provider metadata for dispatcher consumers.

Leaf ``scitex_dev.docs`` declarations are authoritative. Reading this catalog
never loads entry points, imports their targets, executes handlers or adds a
registry fallback. It establishes installed declaration, not live availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Sequence

from packaging.utils import canonicalize_name

__all__ = ["DocProvider", "list_doc_providers"]


@dataclass(frozen=True)
class DocProvider:
    """One leaf-owned installed declaration, without installation paths."""

    name: str
    target: str
    distribution: str
    version: str | None
    summary: str


def list_doc_providers(
    *, path: Sequence[str | Path] | None = None
) -> tuple[DocProvider, ...]:
    """Read installed ``scitex_dev.docs`` declarations without loading code.

    ``path`` optionally restricts metadata discovery to explicit directories;
    by default importlib's installed-distribution search is used. Duplicate
    names are preserved so consumers can report ambiguity rather than choose
    an arbitrary provider. Missing versions remain unknown. Invalid metadata
    raises rather than silently certifying an incomplete catalog.
    """
    distributions = (
        metadata.distributions(path=[str(item) for item in path])
        if path is not None
        else metadata.distributions()
    )
    rows: list[DocProvider] = []
    for distribution in distributions:
        declarations = [
            point for point in distribution.entry_points
            if point.group == "scitex_dev.docs"
        ]
        if not declarations:
            continue
        info = distribution.metadata
        name = info.get("Name")
        if not name:
            raise ValueError("documentation provider distribution lacks Name metadata")
        for point in declarations:
            rows.append(DocProvider(
                name=point.name,
                target=point.value,
                distribution=canonicalize_name(name, validate=True),
                version=info.get("Version") or None,
                summary=info.get("Summary") or "",
            ))
    return tuple(sorted(rows, key=lambda row: (
        row.name, row.distribution, row.target, row.version or "", row.summary
    )))
