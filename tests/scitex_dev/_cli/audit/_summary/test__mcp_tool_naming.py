"""Parameter-object tool names remain valid before and after MCP mounting."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from scitex_dev._cli.audit._summary._mcp_audit import (
    _check_tool_naming,
    _list_tools,
)


@pytest.mark.parametrize(
    "package,name",
    [
        ("scitex-io", "save"),
        ("scitex-io", "io_save"),
        ("scitex-io", "load"),
        ("scitex-io", "io_load"),
        ("scitex-audio", "speak"),
        ("scitex-audio", "audio_speak"),
        ("scitex-plt", "plot"),
        ("scitex-plt", "plt_plot"),
        ("scitex-plt", "compose"),
        ("scitex-plt", "plt_compose"),
    ],
)
def test_parameter_object_names_valid_before_and_after_mount(package, name):
    # Arrange
    violations = []
    # Act
    _check_tool_naming(package, [name], violations)
    # Assert
    assert violations == []


@pytest.mark.parametrize(
    "name",
    ["describe", "stats_describe", "list", "stats_list", "frobnicate"],
)
def test_missing_object_and_unknown_bare_names_still_fail(name):
    # Arrange
    violations = []
    # Act
    _check_tool_naming("scitex-stats", [name], violations)
    # Assert
    assert any(v.rule == "§2" for v in violations)


def test_real_fastmcp_parameter_object_tool_catalog():
    # Arrange
    server = FastMCP("io")

    @server.tool()
    def save(obj: str, path: str) -> str:
        """Save the supplied object to the supplied path."""
        return path

    violations = []
    # Act
    names = [tool.name for tool in _list_tools(server)]
    _check_tool_naming("scitex-io", names, violations)
    # Assert
    assert (names, violations) == (["save"], [])
