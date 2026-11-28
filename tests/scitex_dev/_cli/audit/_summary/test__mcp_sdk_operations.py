"""§2 judges SDK-derived MCP tools by their operation (API-T001, decision 1)."""

from __future__ import annotations

import pytest

pytest.importorskip("scitex_sdk.app.api_ops")

from scitex_dev._cli.audit._summary._mcp_sdk_operations import (
    derived_tool_verbs_of,
)
from scitex_dev._cli.audit._summary._mcp_tool_naming import (
    _check_tool_naming,
)
from scitex_sdk.app.api_ops import ApiOperation, build_plugin

H = "tests:handler"
PLUGIN = build_plugin(
    "notes",
    "Notes",
    "1",
    (
        ApiOperation("notes", "notes", "list", H, paginated=True),
        ApiOperation("notes", "notes", "rm", H, item=True),
        ApiOperation("notes", "cache-entries", "get", H),
    ),
)
DERIVED = derived_tool_verbs_of(PLUGIN)


def _violations(names, derived):
    out = []
    _check_tool_naming("scitex-notes", names, out, derived=derived)
    return [(v.rule, v.command.split("::")[-1]) for v in out]


def test_derived_tools_are_named_package_resource_verb():
    # Arrange
    plugin = PLUGIN
    # Act
    names = sorted(derived_tool_verbs_of(plugin))
    # Assert
    assert names == ["notes_cache_entries_get", "notes_notes_list", "notes_notes_rm"]


def test_a_derived_resource_first_name_is_accepted():
    # Arrange
    names = ["notes_notes_list", "notes_cache_entries_get"]
    # Act
    found = _violations(names, DERIVED)
    # Assert
    assert found == []


def test_a_derived_operation_with_a_banned_verb_is_flagged_by_its_verb():
    # Arrange
    names = ["notes_notes_rm"]
    # Act
    found = _violations(names, DERIVED)
    # Assert
    assert found == [("§2", "notes_notes_rm")]


def test_the_same_name_hand_written_is_still_a_double_prefix():
    # Arrange
    names = ["notes_notes_list"]
    # Act
    found = _violations(names, {})
    # Assert
    assert found == [("§1", "notes_notes_list")]
