"""Resolve a declared Python provider file against installed RECORD metadata.

This does not import code or establish publisher trust, actual import origin,
attribute existence or behavioral correctness. Parent file consistency is
only checked by the explicit chain resolver, never by the target-only resolver.
Only ordinary filesystem .py modules/packages with recorded digests qualify.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path, PurePosixPath

from .._core.names import normalize_distribution_name
from .._core.provider_metadata import ProviderMetadata
from ._capability_providers import read_capability_providers, select_capability_provider


def _provider_record_context(provider, *, path):
    """Read one selected owner's current declaration and raw file records."""
    if not isinstance(provider, ProviderMetadata):
        raise TypeError("provider must be ProviderMetadata")
    current = select_capability_provider(
        read_capability_providers(path=path),
        distribution=provider.distribution, name=provider.name,
    )
    if current != provider:
        raise ValueError("provider declaration changed since discovery")

    # File qualification needs on-disk claims, not cached directory discovery.
    # Keep provider discovery in the shared reader; do not import any target.
    owners = []
    for location in (path if path is not None else sys.path):
        directory = Path(location)
        if not directory.is_dir():
            continue
        for info in directory.glob("*.dist-info"):
            item = metadata.Distribution.at(info)
            name = item.metadata.get("Name")
            if name and normalize_distribution_name(name) == provider.distribution:
                owners.append(item)
    if not owners:
        raise ValueError("provider has no ordinary filesystem distribution metadata")
    if len(owners) != 1:
        raise ValueError("provider distribution ownership is ambiguous")
    dist = owners[0]
    # Distribution.files omits missing paths on supported Python versions.
    # Read the actual manifest so a missing recorded file remains diagnosable.
    text = dist.read_text("RECORD")
    if text is None:
        raise ValueError("provider module must be uniquely listed in RECORD")
    rows = list(csv.reader(io.StringIO(text)))
    if any(len(row) != 3 for row in rows):
        raise ValueError("provider RECORD contains a malformed row")
    return dist, rows


def _resolve_recorded_file(dist, rows, candidates):
    """Verify a file from this owner's manifest without importing any code."""
    records = [row for row in rows if PurePosixPath(row[0]).as_posix() in candidates]
    if len(records) != 1:
        raise ValueError("provider module must be uniquely listed in RECORD")
    relative_record = PurePosixPath(records[0][0])
    hash_field, size_field = records[0][1:]
    root = Path(dist.locate_file("")).resolve()
    located = Path(dist.locate_file(relative_record))
    resolved = located.resolve()
    expected = root / Path(str(relative_record))
    if not resolved.is_relative_to(root) or resolved != expected:
        raise ValueError("provider module path is redirected or outside its distribution")
    if not resolved.is_file():
        raise ValueError("recorded provider module file is missing")
    mode, separator, expected_digest = hash_field.partition("=")
    if not separator or not mode or not expected_digest:
        raise ValueError("provider module RECORD digest is missing")

    digest = hashlib.new(mode)
    size = 0
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    encoded = base64.urlsafe_b64encode(digest.digest()).decode().rstrip("=")
    if encoded != expected_digest:
        raise ValueError("provider module RECORD digest mismatch")
    if size_field and size != int(size_field):
        raise ValueError("provider module RECORD size mismatch")
    return resolved


def resolve_capability_provider_module(
    provider: ProviderMetadata, *, path: Sequence[str | Path] | None = None,
) -> Path:
    """Verify one current declaration's module file without importing its target.

    Refuse stale/ambiguous declarations, missing records, symlink redirects and
    digest/size mismatches. Editable or non-filesystem installs without a
    matching record remain unqualified; no source-tree fallback is attempted.
    The returned file does not establish which module an import would execute.
    """
    dist, rows = _provider_record_context(provider, path=path)
    relative = Path(*provider.target.partition(":")[0].split("."))
    return _resolve_recorded_file(dist, rows, {
        relative.with_suffix(".py").as_posix(),
        (relative / "__init__.py").as_posix(),
    })
