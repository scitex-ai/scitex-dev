#!/usr/bin/env python3
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


@pytest.fixture
def _owned_installed_skill_profile(tmp_path):
    import os

    values = {
        "SCITEX_DIR": str(tmp_path / "state"),
        "SCITEX_DEV_CONFIG": str(tmp_path / "absent.yaml"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _call_registered_skill_tool(name, arguments):
    import asyncio
    import json

    from fastmcp import Client, FastMCP
    from scitex_dev.linter._mcp.tools import register_all_tools

    server = FastMCP("owned-linter-skill-regression")
    register_all_tools(server)

    async def invoke():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    result = asyncio.run(invoke())
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    return json.loads("".join(block.text for block in result.content if block.type == "text"))


def test_mcp_skill_list_reads_actual_installed_linter_namespace(
    _owned_installed_skill_profile,
):
    # Arrange
    from scitex_dev._ecosystem._skills.skills import list_skills

    expected = list_skills(package="scitex-dev-linter")["scitex-dev-linter"]
    # Act
    result = _call_registered_skill_tool("linter_skills_list", {})
    # Assert
    assert (result["success"], result.get("skills")) == (True, expected)


def test_mcp_skill_get_matches_actual_installed_owner_content(
    _owned_installed_skill_profile,
):
    # Arrange
    from scitex_dev._ecosystem._skills.skills import get_skill

    expected = get_skill("scitex-dev-linter", "03_python-api", owner="scitex-dev")
    # Act
    result = _call_registered_skill_tool("linter_skills_get", {"name": "03_python-api"})
    # Assert
    assert (result["success"], result.get("content")) == (True, expected)
