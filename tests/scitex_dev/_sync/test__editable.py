#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: tests/scitex_dev/_sync/test__editable.py

"""Tests for local editable install (uv-first installer + upgrade preflight).

Style note: like the sibling ``test__local.py``, these avoid injected
subprocess runners. The uv-vs-pip branch is driven by ``$PATH``, saved and
restored around each check: an EMPTY ``$PATH`` makes uv undiscoverable, and
a ``$PATH`` holding one real (inert) ``uv`` executable makes it
discoverable. Both directions are supplied by the test.

BOTH directions, because until 2026-08-12 only the pip direction supplied
its own environment. The uv tests asserted the uv branch while doing
nothing to produce a uv — they passed on the author's machine and on the
Spartan runners because uv happened to be installed there, and they failed
the moment CI moved to the scitex-compute nodes, where it is not. A test
that only passes where a tool happens to be installed is measuring the
machine, not the branch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scitex_dev._core.config import DevConfig, PackageConfig
from scitex_dev._sync import sync_local as reexported_sync_local
from scitex_dev._sync._editable import (
    _install_cmd,
    _upgrade_installer_cmds,
    sync_local,
)


class _NoUvPath:
    """Context manager: hide uv (and everything) from ``shutil.which``."""

    def __enter__(self):
        self._saved = os.environ.get("PATH", "")
        os.environ["PATH"] = ""
        return self

    def __exit__(self, *exc):
        os.environ["PATH"] = self._saved
        return False


class _OnlyUvOnPath:
    """Context manager: a ``$PATH`` containing exactly one real ``uv``.

    The mirror image of ``_NoUvPath``, and the reason no mock is needed:
    the branch under test is selected by ``shutil.which("uv")``, whose
    entire question is "is there an executable file named ``uv`` on
    ``$PATH``". So the test writes one. It is a real executable on a real
    ``$PATH``, and the code under test only ever ASKS whether it exists —
    command construction never runs it.

    ``$PATH`` is replaced rather than prepended so the result does not
    change on a machine that also has a real uv installed elsewhere.
    """

    def __init__(self, directory: Path):
        self._dir = directory

    def __enter__(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        stub = self._dir / "uv"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        self._saved = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self._dir)
        return self

    def __exit__(self, *exc):
        os.environ["PATH"] = self._saved
        return False


@pytest.fixture
def one_pkg_config(tmp_path):
    """A DevConfig with a single package whose local_path exists."""
    pkg_dir = tmp_path / "scitex-io"
    pkg_dir.mkdir()
    return DevConfig(
        packages=[
            PackageConfig(
                name="scitex-io",
                local_path=str(pkg_dir),
                pypi_name="scitex-io",
            )
        ]
    )


# ---------------------------------------------------------------------------
# _install_cmd
# ---------------------------------------------------------------------------


def test_install_cmd_uv_branch_builds_uv_editable_command(tmp_path):
    # Arrange
    path = Path("/tmp/pkg")
    # Act
    with _OnlyUvOnPath(tmp_path / "bin"):
        cmd = _install_cmd(path)
    # Assert
    assert cmd == [
        "uv", "pip", "install", "--python", sys.executable, "-e", "/tmp/pkg", "-q"
    ]


def test_install_cmd_without_uv_builds_pip_editable_command():
    # Arrange
    path = Path("/tmp/pkg")
    # Act
    with _NoUvPath():
        cmd = _install_cmd(path)
    # Assert
    assert cmd == [sys.executable, "-m", "pip", "install", "-e", "/tmp/pkg", "-q"]


# ---------------------------------------------------------------------------
# _upgrade_installer_cmds
# ---------------------------------------------------------------------------


def test_upgrade_cmds_uv_branch_updates_uv_then_pip(tmp_path):
    # Arrange
    expected_pip = ["uv", "pip", "install", "--python", sys.executable, "--upgrade", "pip"]
    # Act
    with _OnlyUvOnPath(tmp_path / "bin"):
        cmds = _upgrade_installer_cmds()
    # Assert
    assert cmds == [["uv", "self", "update"], expected_pip]


def test_upgrade_cmds_without_uv_upgrades_pip_only():
    # Arrange
    expected = [[sys.executable, "-m", "pip", "install", "--upgrade", "pip"]]
    # Act
    with _NoUvPath():
        cmds = _upgrade_installer_cmds()
    # Assert
    assert cmds == expected


# ---------------------------------------------------------------------------
# sync_local dry-run
# ---------------------------------------------------------------------------


def test_sync_local_dry_run_row_status_is_dry_run(one_pkg_config):
    # Arrange
    config = one_pkg_config
    # Act
    result = sync_local(confirm=False, config=config)
    # Assert
    assert result["scitex-io"]["status"] == "dry_run"


def test_sync_local_dry_run_previews_uv_install_cmd(one_pkg_config):
    # Arrange
    pkg_path = Path(one_pkg_config.packages[0].local_path)
    # Act
    result = sync_local(confirm=False, config=one_pkg_config)
    # Assert
    assert result["scitex-io"]["commands"] == _install_cmd(pkg_path)


def test_sync_local_dry_run_includes_preflight_key(one_pkg_config):
    # Arrange
    config = one_pkg_config
    # Act
    result = sync_local(confirm=False, config=config)
    # Assert
    assert result["_preflight"]["commands"] == _upgrade_installer_cmds()


def test_sync_local_skips_missing_package_path(tmp_path):
    # Arrange
    config = DevConfig(
        packages=[
            PackageConfig(
                name="ghost",
                local_path=str(tmp_path / "does-not-exist"),
                pypi_name="ghost",
            )
        ]
    )
    # Act
    result = sync_local(confirm=False, config=config)
    # Assert
    assert result["ghost"]["status"] == "skipped"


def test_sync_local_dry_run_no_preflight_when_nothing_installable(tmp_path):
    # Arrange
    config = DevConfig(
        packages=[
            PackageConfig(
                name="ghost",
                local_path=str(tmp_path / "does-not-exist"),
                pypi_name="ghost",
            )
        ]
    )
    # Act
    result = sync_local(confirm=False, config=config)
    # Assert
    assert "_preflight" not in result


def test_reexport_from_sync_package_is_same_callable():
    # Arrange
    # Act
    # Assert
    assert reexported_sync_local is sync_local
