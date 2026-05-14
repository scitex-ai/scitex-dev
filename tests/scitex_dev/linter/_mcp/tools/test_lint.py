"""Tests for the linter MCP tools registration.

The module exports `register_lint_tools(mcp)` which the host MCP
server calls to attach lint-related tools. We exercise that
registration against a real in-process tool registry so that an
accidental rename or missing decoration trips the test.
"""

from __future__ import annotations

import pytest


class _RecordingMCP:
    """Tiny stand-in for a fastmcp server: records every tool registered.

    Real fastmcp's `@mcp.tool()` decorator returns a decorator; we
    mirror that shape so production code that uses `@mcp.tool()` lands
    its callables in our `tools` list.
    """

    def __init__(self) -> None:
        self.tools: list[str] = []

    def tool(self, *_args, **_kwargs):
        def _decorator(fn):
            self.tools.append(fn.__name__)
            return fn

        return _decorator


def test_register_lint_tools_attaches_at_least_one_tool():
    """Calling `register_lint_tools(mcp)` must register one or more
    tools on the passed MCP-like object. Catches the regression where
    the registration body becomes empty after a refactor."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.linter._mcp.tools.lint import register_lint_tools

    mcp = _RecordingMCP()
    register_lint_tools(mcp)
    assert len(mcp.tools) > 0


@pytest.fixture
def _registered_lint_tool_names():
    from scitex_dev.linter._mcp.tools.lint import register_lint_tools

    mcp = _RecordingMCP()
    register_lint_tools(mcp)
    return list(mcp.tools)


def test_register_lint_tools_tool_names_are_lowercase(_registered_lint_tool_names):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    lowered = [n == n.lower() for n in names]
    # Assert
    assert all(lowered)


def test_register_lint_tools_tool_names_contain_no_spaces(_registered_lint_tool_names):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    has_space = [" " in n for n in names]
    # Assert
    assert not any(has_space)


def test_register_lint_tools_tool_names_are_python_identifiers(
    _registered_lint_tool_names,
):
    # Arrange
    names = _registered_lint_tool_names
    # Act
    valid = [n.isidentifier() for n in names]
    # Assert
    assert all(valid)
