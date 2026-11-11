"""Installed CLI declarations, independent of Python, MCP and skills policy.

Discovery reads metadata only. ``declared`` means an owned entry-point target,
not a callable or Click command; hosts must resolve those only on invocation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import tomllib
except ImportError:  # Python 3.9/3.10
    import tomli as tomllib

from .._core.names import normalize_distribution_name
from ._metadata_snapshot import _MetadataSnapshot

__all__ = ["CliProvider", "list_cli_providers"]

_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_TARGET = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z", re.ASCII
)
_BRANDS = frozenset(
    {"figrecipe", "socialia", "newb", "crossref-local", "openalex-local"}
)


@dataclass(frozen=True)
class CliProvider:
    """One declaration/evidence row; non-eligible rows must not be mounted.

    Names on ``none``, ``invalid`` and ``ambiguous`` rows are reserved too:
    wrapper/registry fallback must never resurrect them. Only ``declared`` and
    ``legacy_unknown`` are candidates for lazy invocation-time validation.
    """

    name: str | None
    target: str | None
    distribution: str | None
    version: str | None
    status: str
    source: str
    console_script: str | None = None
    reason: str = ""


def _editable_root(dist, owner: str) -> Path | None:
    """Validate a local editable source identity without executing .pth files."""
    try:
        direct = json.loads(dist.read_text("direct_url.json") or "null")
        if (
            not isinstance(direct, dict)
            or direct.get("dir_info", {}).get("editable") is not True
        ):
            return None
        url = urlsplit(direct["url"])
        if (
            url.scheme != "file"
            or url.netloc not in ("", "localhost")
            or url.query
            or url.fragment
        ):
            return None
        root = Path(unquote(url.path))
        if not root.is_absolute():
            return None
        root = root.resolve(strict=True)
        project = root / "pyproject.toml"
        if not project.resolve(strict=True).is_relative_to(root):
            return None
        data = tomllib.loads(project.read_text())
        return (
            root
            if normalize_distribution_name(data["project"]["name"]) == owner
            else None
        )
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return None


def _editable_owns_module(dist, owner: str, module: str) -> bool:
    root = _editable_root(dist, owner)
    if root is None:
        return False
    try:
        candidates = [
            base / suffix
            for base in (root, root / "src")
            for suffix in (module + ".py", module + "/__init__.py")
        ]
        found = [file for file in candidates if file.is_file()]
        return len(found) == 1 and found[0].resolve(strict=True).is_relative_to(root)
    except OSError:
        return False


def _metadata_origin(dist) -> Path | None:
    # PathDistribution exposes no public metadata-directory identity. Do not
    # guess for other Distribution implementations; retain their ambiguity.
    origin = getattr(dist, "_path", None)
    return Path(origin).resolve() if isinstance(origin, (str, Path)) else None


def _distinct_installs(distributions, snapshot=None):
    """Dedup repeated origins and exactly proved editable source shadows only."""
    snapshot = snapshot or _MetadataSnapshot()
    unique, seen = [], set()
    for dist in distributions:
        origin = _metadata_origin(dist)
        if origin is not None and origin in seen:
            continue
        if origin is not None:
            seen.add(origin)
        unique.append(dist)
    shadows = set()
    for installed in unique:
        try:
            owner = normalize_distribution_name(snapshot.headers(installed).get("Name"))
        except ValueError:
            continue
        root = _editable_root(installed, owner)
        origin = _metadata_origin(installed)
        if root is None or origin is None or origin.suffix != ".dist-info":
            continue
        for source in unique:
            source_origin = _metadata_origin(source)
            if source_origin is None or source_origin.suffix != ".egg-info":
                continue
            if source_origin.parent not in (root, root / "src"):
                continue
            if (
                source.read_text("PKG-INFO") is not None
                and source.read_text("PKG-INFO") == installed.read_text("METADATA")
                and snapshot.version(source) == snapshot.version(installed)
                and sorted((ep.group, ep.name, ep.value) for ep in source.entry_points)
                == sorted(
                    (ep.group, ep.name, ep.value) for ep in installed.entry_points
                )
            ):
                shadows.add(source_origin)
    return [dist for dist in unique if _metadata_origin(dist) not in shadows]


def _owns_module(dist, owner: str, target: str) -> bool:
    """Require exact wheel files or an owned conventional local editable source."""
    module = target.partition(":")[0].replace(".", "/")
    candidates = {module + ".py", module + "/__init__.py"}
    return any(
        str(file).replace("\\", "/") in candidates for file in (dist.files or ())
    ) or _editable_owns_module(dist, owner, module)


def _rows(dist, owner: str | None, snapshot=None) -> list[CliProvider]:
    snapshot = snapshot or _MetadataSnapshot()
    entries = tuple(dist.entry_points)
    explicit = [ep for ep in entries if ep.group == "scitex.cli"]
    base = {"distribution": owner, "version": snapshot.version(dist)}
    if explicit:
        rows = []
        for ep in explicit:
            reason = ""
            status = "declared"
            target = ep.value
            if owner is None or not _NAME.fullmatch(ep.name):
                status, reason = (
                    "invalid",
                    "invalid declaring distribution or command name",
                )
            elif target == "none":
                status, target = "none", None
            elif not _TARGET.fullmatch(target) or not _owns_module(dist, owner, target):
                status, reason = (
                    "invalid",
                    "target syntax or installed file ownership is unproven",
                )
            rows.append(
                CliProvider(
                    ep.name,
                    target,
                    **base,
                    status=status,
                    source="scitex.cli",
                    reason=reason,
                )
            )
        return rows
    consoles = [
        ep for ep in entries if ep.group == "console_scripts" and ep.name == owner
    ]
    if owner and (owner.startswith("scitex-") or owner in _BRANDS) and consoles:
        name = owner.removeprefix("scitex-")
        if name == "socialia":
            name = "social"
        return [
            (
                CliProvider(
                    name,
                    ep.value,
                    **base,
                    status="legacy_unknown",
                    source="console_scripts",
                    console_script=ep.name,
                    reason="legacy canonical console; invocation not verified",
                )
                if _TARGET.fullmatch(ep.value) and _owns_module(dist, owner, ep.value)
                else CliProvider(
                    name,
                    ep.value,
                    **base,
                    status="invalid",
                    source="console_scripts",
                    console_script=ep.name,
                    reason="legacy target syntax or installed file ownership is unproven",
                )
            )
            for ep in consoles
        ]
    return [
        CliProvider(
            None,
            None,
            **base,
            status="absent",
            source="installed_metadata",
            reason="no CLI declaration or eligible canonical console",
        )
    ]


def list_cli_providers(
    *,
    package: str | None = None,
    path: Sequence[str | Path] | None = None,
) -> tuple[CliProvider, ...]:
    """Read installed declarations without loading entry points or leaf modules.

    Explicit declarations suppress legacy fallback for their entire owner.
    Duplicated owners and command names are ambiguous, including opt-out names.
    Ambiguity is determined BEFORE an optional owner filter. ``path`` limits the
    metadata search (useful for isolated environments and real dist-info tests).
    Installed headers share one snapshot within this call; a subsequent call
    reads installed state again rather than reusing a process-global cache.
    """
    selected = normalize_distribution_name(package) if package is not None else None
    snapshot = _MetadataSnapshot()
    distributions = _distinct_installs(
        metadata.distributions(
            **({"path": [str(p) for p in path]} if path is not None else {})
        ),
        snapshot=snapshot,
    )
    rows = []
    owners = []
    for dist in distributions:
        try:
            owner = normalize_distribution_name(snapshot.headers(dist).get("Name"))
        except ValueError:
            owner = None
        owners.append(owner)
        rows.extend(_rows(dist, owner, snapshot=snapshot))
    owner_counts = Counter(owner for owner in owners if owner is not None)
    name_counts = Counter(row.name for row in rows if row.name is not None)
    rows = [
        (
            replace(
                row,
                status="ambiguous",
                reason="duplicate installed owner or command name",
            )
            if owner_counts[row.distribution] > 1
            or (row.name is not None and name_counts[row.name] > 1)
            else row
        )
        for row in rows
    ]
    return tuple(
        sorted(
            (row for row in rows if selected is None or row.distribution == selected),
            key=lambda row: (row.name or "", row.distribution or "", row.target or ""),
        )
    )
