"""Read installed hierarchy declarations without executing provider code."""

from __future__ import annotations

import json
import re
from importlib.util import find_spec
from pathlib import Path
from typing import Sequence

from .._core.provider_metadata import read_provider_metadata
from ._schema import PackageHierarchy, validate_package_hierarchy

_RESOURCE = "_package_hierarchy.json"
_MAX_BYTES = 2 * 1024 * 1024


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field in hierarchy")
        result[key] = value
    return result


def list_package_hierarchies(*, path: Sequence[str | Path] | None = None) -> tuple[PackageHierarchy, ...]:
    """Discover scitex_dev.hierarchy catalogs, failing on conflicting claims.

    Entry-point values name top-level Python packages, never callables. Their
    fixed JSON resource is read without loading the entry point or importing
    provider code. ``path`` limits distribution metadata search only; package
    locations follow the interpreter's normal import path. These declarations
    describe navigation, not installed package availability or host admission.
    """
    catalogs = []
    roots: set[str] = set()
    all_ids: set[str] = set()
    all_distributions: set[str] = set()
    for provider in read_provider_metadata("scitex_dev.hierarchy", path=path):
        if provider.name in roots:
            raise ValueError("duplicate hierarchy provider: " + provider.name)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", provider.target):
            raise ValueError("hierarchy target must be a top-level package")
        spec = find_spec(provider.target)
        locations = None if spec is None else spec.submodule_search_locations
        if locations is None or len(locations) != 1:
            raise ValueError("hierarchy package must have one unambiguous location")
        package = Path(next(iter(locations))).resolve(strict=True)
        resource = package / _RESOURCE
        if resource.is_symlink() or resource.resolve(strict=True).parent != package:
            raise ValueError("hierarchy resource must be a regular package file")
        with resource.open("rb") as stream:
            content = stream.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise ValueError("hierarchy resource exceeds 2 MiB")
        catalog = validate_package_hierarchy(json.loads(content, object_pairs_hook=_unique_keys))
        if catalog.root != provider.name:
            raise ValueError("hierarchy root must match provider name")
        identities = {node.id for node in catalog.nodes}
        distributions = {node.distribution for node in catalog.nodes if node.distribution}
        if all_ids & identities or all_distributions & distributions:
            raise ValueError("conflicting hierarchy catalog identities")
        roots.add(catalog.root)
        all_ids.update(identities)
        all_distributions.update(distributions)
        catalogs.append(catalog)
    return tuple(catalogs)
