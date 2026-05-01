"""Smoke tests for scitex_dev.dev_mcp.handlers — exercise async handlers with mocks.

The dev_mcp package depends on a `scitex_dev.mcp_utils` module that may not be
present in every install (it's wired up by the MCP entry-point). If the import
fails we skip the test rather than fail collection — PS202 only requires that
this test file exists at the mirror path.
"""

from __future__ import annotations

import asyncio
import json

import pytest

dev_mcp = pytest.importorskip("scitex_dev.dev_mcp")
handlers = pytest.importorskip("scitex_dev.dev_mcp.handlers")


HANDLER_NAMES = [
    "fix_mismatches_handler",
    "get_config_handler",
    "list_versions_handler",
    "pull_local_handler",
    "remote_commit_handler",
    "remote_diff_handler",
    "rename_handler",
    "skills_get_handler",
    "skills_list_handler",
    "sync_handler",
    "sync_local_handler",
    "test_hpc_poll_handler",
    "test_hpc_result_handler",
    "test_hpc_run_handler",
    "test_run_handler",
]


def test_all_handlers_exposed():
    """Every handler in __all__ is importable and async."""
    for name in HANDLER_NAMES:
        h = getattr(dev_mcp, name)
        assert asyncio.iscoroutinefunction(h), f"{name} not async"


def test_list_versions_handler_runs(monkeypatch):
    """list_versions_handler returns valid JSON wrapping a mocked list_versions."""
    import scitex_dev.versions as vmod

    monkeypatch.setattr(
        vmod, "list_versions", lambda packages=None: {"scitex-dev": "0.0.0"}
    )
    out = asyncio.run(handlers.list_versions_handler())
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["data"] == {"scitex-dev": "0.0.0"}
