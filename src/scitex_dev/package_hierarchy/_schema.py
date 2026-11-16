"""Inert, versioned package navigation metadata shared by UI consumers."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .._core.names import normalize_distribution_name

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_INDEX = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[1-9][0-9]*)*\Z")


@dataclass(frozen=True)
class HierarchyNode:
    """Stable identity and display position, independent of installation order."""

    id: str
    label: str
    index: str
    parent_id: str | None
    kind: str
    distribution: str | None = None


@dataclass(frozen=True)
class PackageHierarchy:
    """Validated catalog; packages may be absent from the current environment."""

    root: str
    nodes: tuple[HierarchyNode, ...]
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible contract for SDK and host consumers."""
        return {"schema_version": self.schema_version, "root": self.root,
                "nodes": [asdict(node) for node in self.nodes]}


def validate_package_hierarchy(data: object) -> PackageHierarchy:
    """Reject ambiguous identities, invalid parents and inconsistent indices.

    This validates navigation metadata only: no imports, dependency graph,
    runtime enablement or live capability checks are performed.
    """
    if not isinstance(data, dict) or set(data) != {"schema_version", "root", "nodes"}:
        raise ValueError("hierarchy requires schema_version, root and nodes only")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported hierarchy schema_version")
    root = data["root"]
    if not isinstance(root, str) or not _ID.fullmatch(root):
        raise ValueError("invalid hierarchy root")
    rows = data["nodes"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("hierarchy requires 1 to 10000 nodes")
    nodes: dict[str, HierarchyNode] = {}
    indices: set[str] = set()
    distributions: set[str] = set()
    required = {"id", "label", "index", "parent_id", "kind"}
    for row in rows:
        if not isinstance(row, dict) or not required <= row.keys() or row.keys() - required - {"distribution"}:
            raise ValueError("invalid hierarchy node fields")
        identity, label, index = row["id"], row["label"], row["index"]
        parent, kind, distribution = row["parent_id"], row["kind"], row.get("distribution")
        if not isinstance(identity, str) or not _ID.fullmatch(identity) or identity in nodes:
            raise ValueError("invalid or duplicate hierarchy node id")
        if not isinstance(label, str) or not label.strip() or len(label) > 256:
            raise ValueError("invalid hierarchy label")
        if not isinstance(index, str) or len(index) > 128 or not _INDEX.fullmatch(index) or index in indices:
            raise ValueError("invalid or duplicate hierarchy index")
        if parent is not None and (not isinstance(parent, str) or not _ID.fullmatch(parent)):
            raise ValueError("invalid hierarchy parent")
        if kind not in ("root", "group", "package"):
            raise ValueError("invalid hierarchy node kind")
        if kind == "package":
            if not isinstance(distribution, str) or normalize_distribution_name(distribution) != distribution:
                raise ValueError("package requires canonical distribution name")
            if distribution in distributions:
                raise ValueError("duplicate hierarchy distribution")
            distributions.add(distribution)
        elif distribution is not None:
            raise ValueError("only package nodes may name a distribution")
        nodes[identity] = HierarchyNode(identity, label, index, parent, kind, distribution)
        indices.add(index)
    if root not in nodes or nodes[root].kind != "root" or nodes[root].index != "0" or nodes[root].parent_id is not None:
        raise ValueError("root must have kind root, index 0 and no parent")
    for node in nodes.values():
        if node.id == root:
            continue
        if node.kind == "root" or node.parent_id not in nodes:
            raise ValueError("non-root requires a known parent")
        parent = nodes[node.parent_id]
        if parent.kind == "package":
            raise ValueError("package nodes cannot contain children")
        prefix = "" if parent.id == root else parent.index + "."
        suffix = node.index.removeprefix(prefix)
        if not node.index.startswith(prefix) or not re.fullmatch(r"[1-9][0-9]*", suffix):
            raise ValueError("child index must extend its parent by one positive segment")
    # Strictly increasing index depth on each edge proves reachability and
    # excludes cycles without recursion or dependence on input ordering.
    ordered = tuple(sorted(nodes.values(), key=lambda node: tuple(map(int, node.index.split(".")))))
    return PackageHierarchy(root, ordered)
