#!/usr/bin/env python3
"""Tests for the auto-loaded pytest test-execution guard plugin.

The guard's decision logic is exercised directly (no real pytest run is
broken). One test proves it stays inert in this very checkout (default mode =
local → scitex-dev's own CI is never blocked); another drives the raise path
with a real remote-required recipe under a tmp git scope, cwd swapped in/out
(no mocks/monkeypatch).
"""

from __future__ import annotations

import os

import pytest

from scitex_dev._core._test_execution_plugin import pytest_configure


def test_plugin_inert_in_this_checkout():
    # Arrange
    config = None
    # Act
    result = pytest_configure(config)
    # Assert
    assert result is None


def test_plugin_raises_usage_error_on_remote_required(tmp_path):
    # Arrange
    (tmp_path / ".git").mkdir()
    scope = tmp_path / ".scitex" / "io"
    scope.mkdir(parents=True)
    (scope / "test-execution.yaml").write_text("mode: remote-required\n")
    prev_cwd = os.getcwd()
    os.chdir(tmp_path)
    raised = False
    # Act
    try:
        pytest_configure(None)
    except pytest.UsageError:
        raised = True
    finally:
        os.chdir(prev_cwd)
    # Assert
    assert raised is True


# EOF
