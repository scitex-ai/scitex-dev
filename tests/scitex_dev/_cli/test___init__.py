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

from scitex_dev._cli import _is_bare_version_invocation, _should_fast_path_version


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


# --------------------------------------------------------------------------
# argv[0] gate — a DOWNSTREAM package importing this shared primitive must
# never be hijacked into reporting scitex-dev's identity.
#
# Regression: `scitex-ui --version` / `scitex-app --version` printed
# `scitex-dev <ver>` because the fast path matched on argv[1:] alone, then
# printed and raised SystemExit(0) during `import scitex_dev._cli`.
# --------------------------------------------------------------------------

_DOWNSTREAM_IMPORT = (
    "import sys; sys.argv=['scitex-ui', '--version']; "
    "import scitex_dev._cli; print('IMPORT-COMPLETED')"
)


def test_downstream_console_script_is_not_fast_pathed():
    # Arrange
    argv0, rest = "/venv/bin/scitex-ui", ["--version"]
    # Act
    result = _should_fast_path_version([argv0, *rest])
    # Assert
    assert result is False


def test_own_console_script_is_fast_pathed():
    # Arrange
    argv0, rest = "/venv/bin/scitex-dev", ["--version"]
    # Act
    result = _should_fast_path_version([argv0, *rest])
    # Assert
    assert result is True


def test_python_dash_m_entry_point_is_fast_pathed():
    # Arrange
    argv0, rest = "/site-packages/scitex_dev/__main__.py", ["-V"]
    # Act
    result = _should_fast_path_version([argv0, *rest])
    # Assert
    assert result is True


def test_unrecognised_argv0_declines_the_optimisation():
    # Arrange — cannot prove we are scitex-dev, so we must NOT claim to be
    argv0, rest = "", ["--version"]
    # Act
    result = _should_fast_path_version([argv0, *rest])
    # Assert
    assert result is False


def test_downstream_import_does_not_print_scitex_dev_identity():
    # Arrange
    argv = [sys.executable, "-c", _DOWNSTREAM_IMPORT]
    # Act
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    # Assert
    assert "scitex-dev " not in proc.stdout


def test_downstream_import_is_not_killed_by_system_exit():
    # Arrange
    argv = [sys.executable, "-c", _DOWNSTREAM_IMPORT]
    # Act
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    # Assert
    assert "IMPORT-COMPLETED" in proc.stdout
