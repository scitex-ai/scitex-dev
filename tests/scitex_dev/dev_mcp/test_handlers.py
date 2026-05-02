"""Smoke tests for scitex_dev.dev_mcp.handlers — exercise async handlers with mocks.

handlers.py imports `wrap_as_mcp` from `scitex_dev._mcp` (the post-0.11
collapsed package). If the import fails for any reason (e.g. partial
install) we skip rather than fail collection.
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
