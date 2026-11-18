"""Dev-owned package hierarchy declaration, independent of discovery.

Plain declarations need no SDK import. Explicit typed-record loading uses the
SDK contract when that capability is installed; it never duplicates validation.
"""

from __future__ import annotations

__all__ = ["get_hierarchy_declarations", "get_hierarchy_nodes"]

_DECLARATIONS = (
    {
        "id": "package:scitex-dev",
        "distribution": "scitex-dev",
        "index": "3.4",
        "label": "scitex-dev",
        "parent_id": "scitex.intermediate",
    },
)


def get_hierarchy_declarations() -> tuple[dict[str, str | None], ...]:
    """Return independent JSON-shaped copies of the Dev declaration.

    Dev owns only its package slot 3.4. The umbrella owns root/layers;
    other leaves declare their own allocations. This is taxonomy, not
    dependencies, installed presence, permission or live availability.
    """
    return tuple(dict(node) for node in _DECLARATIONS)


def get_hierarchy_nodes() -> tuple[object, ...]:
    """Build Dev's SDK HierarchyNode instance on explicit request.

    Requires the installed SDK hierarchy capability, not merely a matching
    version string. Metadata discovery and plain declaration access need no
    SDK. SDK owns node/tree validation; this function invents no leaf slots and
    performs no provider discovery, host admission or service operation.

    Raises
    ------
        RuntimeError: The SDK hierarchy module is not installed.
    """
    try:
        from scitex_sdk.hierarchy import HierarchyNode
    except ModuleNotFoundError as exc:
        if exc.name not in {"scitex_sdk", "scitex_sdk.hierarchy"}:
            raise
        raise RuntimeError(
            "Typed hierarchy records require the SDK hierarchy contract. "
            "Use get_hierarchy_declarations() to inspect metadata without it."
        ) from exc
    return tuple(HierarchyNode(**node) for node in get_hierarchy_declarations())
