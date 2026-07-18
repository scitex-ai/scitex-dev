#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: tests/scitex_dev/_cli/test___init__.py

"""Tests for the `--version`/`-V` fast path in `scitex_dev._cli`.

`_root`'s module-level code eagerly registers the entire subcommand
tree (several hundred ms of imports). `_is_bare_version_invocation`
lets `__init__.py` skip that import for a bare version check; these
tests cover the predicate directly (no subprocess needed) plus one
end-to-end subprocess test proving the real console-script path.
"""

from __future__ import annotations

import subprocess
import sys

from scitex_dev._cli import _is_bare_version_invocation


def test_bare_version_flag_is_fast_path():
    # Arrange
    argv = ["--version"]
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is True


def test_short_version_flag_is_fast_path():
    # Arrange
    argv = ["-V"]
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is True


def test_version_combined_with_json_is_not_fast_path():
    # Arrange
    argv = ["--version", "--json"]
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is False


def test_subcommand_is_not_fast_path():
    # Arrange
    argv = ["ecosystem", "list"]
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is False


def test_no_args_is_not_fast_path():
    # Arrange
    argv = []
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is False


def test_subcommand_with_version_flag_is_not_fast_path():
    # Arrange
    argv = ["mcp", "--version"]
    # Act
    result = _is_bare_version_invocation(argv)
    # Assert
    assert result is False


def test_real_process_version_invocation_prints_scitex_dev_prefix():
    # Arrange
    argv = [sys.executable, "-c", "import sys; sys.argv=['scitex-dev', '--version']; import scitex_dev._cli"]
    # Act
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    # Assert
    assert proc.stdout.strip().startswith("scitex-dev ")


def test_real_process_version_invocation_exits_zero():
    # Arrange
    argv = [sys.executable, "-c", "import sys; sys.argv=['scitex-dev', '--version']; import scitex_dev._cli"]
    # Act
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    # Assert
    assert proc.returncode == 0
