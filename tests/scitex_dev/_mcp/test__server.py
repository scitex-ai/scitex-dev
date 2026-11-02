#!/usr/bin/env python3
"""Registered MCP server and repair preview/apply contracts; no live services."""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from scitex_dev._ecosystem._mcp import get_tools_sync
from scitex_dev._mcp._server import mcp


@pytest.mark.parametrize(
    "arguments,confirmed",
    [({}, False), ({"dry_run": True}, False), ({"dry_run": False}, True)],
)
def test_registered_tool_routes_confirmation_to_actual_coordinator(
    tmp_path, monkeypatch, arguments, confirmed
):
    """Only explicit apply permits the owned local/remote service mutations."""
    # Arrange
    from scitex_dev._release import fix

    calls = []
    config = object()
    package = "owned-fixture-package"

    def local_boundary(*, packages, confirm, config):
        calls.append(("local", packages, confirm))
        if confirm:
            (tmp_path / "local-applied").write_text(package)
        return {package: {"status": "ok" if confirm else "dry_run"}}

    def remote_boundary(*, hosts, packages, confirm, config):
        calls.append(("remote", packages, confirm))
        if confirm:
            (tmp_path / "remote-applied").write_text(package)
        return {
            "owned-fixture-host": {package: {"status": "ok" if confirm else "dry_run"}}
        }

    monkeypatch.setattr(fix, "load_config", lambda: config)
    monkeypatch.setattr(
        fix,
        "get_mismatches",
        lambda packages: {
            package: {
                "status": "mismatch",
                "issues": ["owned fixture"],
                "local": {"pyproject_toml": "2.0.0", "installed": "1.0.0"},
            }
        },
    )
    monkeypatch.setattr(fix, "fix_local", local_boundary)
    monkeypatch.setattr(fix, "fix_remote", remote_boundary)
    tool = get_tools_sync(mcp)["dev_ecosystem_fix_mismatches"]
    # Act
    payload = json.loads(asyncio.run(tool.fn(**arguments)))
    observed = {
        "success": payload["success"],
        "calls": calls,
        "files": sorted(path.name for path in tmp_path.iterdir()),
        "summary": payload["data"]["summary"],
    }
    # Assert
    assert observed == {
        "success": True,
        "calls": [("local", [package], confirmed), ("remote", [package], confirmed)],
        "files": ["local-applied", "remote-applied"] if confirmed else [],
        "summary": {
            "detected": 1,
            "local_fixed": int(confirmed),
            "remote_fixed": int(confirmed),
        },
    }


def test_registered_tool_keeps_its_advertised_safe_default():
    """The existing name, sole Boolean parameter and preview default remain."""
    # Arrange
    tool = get_tools_sync(mcp)["dev_ecosystem_fix_mismatches"]
    # Act
    signature = inspect.signature(tool.fn)
    parameter = signature.parameters["dry_run"]
    observed = {
        "name": tool.name,
        "parameters": list(signature.parameters),
        "default": parameter.default,
        "schema_type": tool.parameters["properties"]["dry_run"]["type"],
        "schema_default": tool.parameters["properties"]["dry_run"]["default"],
    }
    # Assert
    assert observed == {
        "name": "dev_ecosystem_fix_mismatches",
        "parameters": ["dry_run"],
        "default": True,
        "schema_type": "boolean",
        "schema_default": True,
    }


def test_server_module_importable_hasattr__server_mcp():
    # Arrange
    # Act
    # Assert
    from scitex_dev._mcp import _server

    assert hasattr(_server, "mcp")


def test_server_module_importable_server_mcp_name_scitex_dev():
    # Arrange
    # Act
    # Assert
    from scitex_dev._mcp import _server

    assert _server.mcp.name == "scitex-dev"
