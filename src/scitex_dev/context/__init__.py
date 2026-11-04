"""Upstream MCP discovery and vendor-neutral context accounting.

These helpers operate on caller-selected servers and metadata. They neither
discover/import leaf handlers nor read an agent's conversation or credentials.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

_SKILL_BODY_FIELDS = {"body", "content", "text", "instructions"}


def _json_size(value: Any) -> dict[str, int]:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {"characters": len(text), "utf8_bytes": len(text.encode("utf-8"))}


def _selected_items(items, kind):
    if isinstance(items, (str, bytes, Mapping)) or not isinstance(items, Sequence):
        raise TypeError(f"{kind} must be a sequence of metadata mappings")
    selected, names = [], set()
    for item in items:
        if not isinstance(item, Mapping):
            raise TypeError(f"{kind} requires metadata mappings")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{kind} requires a nonempty name")
        if name in names:
            raise ValueError(f"{kind} names must be unique within the snapshot")
        if kind == "skill_header" and _SKILL_BODY_FIELDS.intersection(item):
            raise ValueError(
                "skill_headers must not contain body/content/text/instructions"
            )
        names.add(name)
        selected.append(dict(item))
    return selected


def _owners(owners):
    if owners is None:
        return {}
    if not isinstance(owners, Mapping):
        raise TypeError("owner attribution must be an explicit mapping")
    if any(
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(owner, str)
        or not owner.strip()
        or owner == "unattributed"
        for name, owner in owners.items()
    ):
        raise ValueError(
            "owner names must be nonempty strings; unattributed is reserved"
        )
    return owners


def configure_mcp_discovery(
    server: Any,
    *,
    search: bool = True,
    max_results: int = 5,
    always_visible: Sequence[str] = (),
) -> None:
    """Attach FastMCP's existing search transform to a configured server.

    Apply the host's selection/authorization policy first. This transform
    reduces advertised definitions; it does not grant or revoke permission.
    Unsupported FastMCP versions fail explicitly, never exposing a full catalog
    as a silent fallback. Call once when constructing the server.
    """
    if not isinstance(search, bool):
        raise TypeError("search must be a boolean")
    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or max_results < 1
    ):
        raise ValueError("max_results must be a positive integer")
    if not search:
        return
    if isinstance(always_visible, (str, bytes)) or not isinstance(
        always_visible, Sequence
    ):
        raise TypeError("always_visible must be a sequence of tool names")
    if any(not isinstance(name, str) or not name.strip() for name in always_visible):
        raise ValueError("always_visible requires nonempty tool names")
    try:
        from fastmcp.server.transforms.search import RegexSearchTransform
    except ImportError as exc:
        raise RuntimeError(
            "MCP search requires FastMCP RegexSearchTransform support"
        ) from exc

    server.add_transform(
        RegexSearchTransform(
            max_results=max_results, always_visible=list(always_visible)
        )
    )


def measure_context(
    *,
    tools: Sequence[Mapping[str, Any]] = (),
    skill_headers: Sequence[Mapping[str, Any]] = (),
    instructions: str = "",
    tool_owners: Mapping[str, str] | None = None,
    skill_owners: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Measure selected metadata without inventing a vendor token count.

    Supply actual advertised MCP tool definitions and selected skill headers,
    not the complete installed catalog or full skill bodies. Ownership must
    come from the provider registry: name prefixes are never ownership proof.
    Names must be unique within each input list; use existing registry-qualified
    skill identities when needed. Body/content/text/instructions fields are
    rejected in skill headers. Owner values must be nonempty strings; the
    unattributed aggregate bucket is reserved. Missing ownership is unattributed.
    Measurements describe a normalized snapshot, not protocol framing or the
    client's complete prompt. Characters are Unicode code points, not tokens.
    No inputs or tool descriptions are reproduced in the returned report.
    """
    if not isinstance(instructions, str):
        raise TypeError("instructions must be text")

    tools = _selected_items(tools, "mcp_tool")
    skill_headers = _selected_items(skill_headers, "skill_header")
    tool_owners, skill_owners = _owners(tool_owners), _owners(skill_owners)

    rows = []
    for kind, items, owners in (
        ("mcp_tool", tools, tool_owners or {}),
        ("skill_header", skill_headers, skill_owners or {}),
    ):
        for item in items:
            name = item.get("name")
            rows.append(
                {
                    "kind": kind,
                    "name": name,
                    "owner": owners.get(name),
                    "ownership": "declared" if name in owners else "unattributed",
                    **_json_size(item),
                }
            )
    packages: dict[str, dict[str, int]] = {}
    for row in rows:
        group = packages.setdefault(
            row["owner"] or "unattributed",
            {"mcp_tools": 0, "skill_headers": 0, "characters": 0, "utf8_bytes": 0},
        )
        group["mcp_tools" if row["kind"] == "mcp_tool" else "skill_headers"] += 1
        group["characters"] += row["characters"]
        group["utf8_bytes"] += row["utf8_bytes"]
    snapshot = {
        "tools": [dict(item) for item in tools],
        "skill_headers": [dict(item) for item in skill_headers],
        "instructions": instructions,
    }
    return {
        "schema_version": "scitex-context-report/1",
        "scope": "caller_supplied_advertised_metadata",
        "normalization": "UTF-8 compact sorted-key JSON; not protocol framing",
        "total": _json_size(snapshot),
        "instructions": _json_size(instructions),
        "instructions_measurement": "serialized_json_string",
        "instructions_raw": {
            "characters": len(instructions),
            "utf8_bytes": len(instructions.encode("utf-8")),
        },
        "packages": dict(sorted(packages.items())),
        "items": rows,
        "tokens": None,
        "tokenizer": None,
        "client_total_context": "not_observed",
        "notes": [
            "Package/item sums exclude snapshot framing and shared instructions.",
            "Skill bodies and tool results are not fetched; "
            "caller supplies selected headers only.",
            "Discovery visibility does not establish authorization or runtime health.",
        ],
    }


__all__ = ["configure_mcp_discovery", "measure_context"]
