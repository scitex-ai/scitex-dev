#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The four "did it ship / is it running?" checks, on recorded incident data.

Each returns a pure verdict; ``None`` inputs are UNKNOWN, never "fine".
"""

from __future__ import annotations

from scitex_dev.versioning._model import Currency
from scitex_dev.versioning._ship_checks import (
    check_ghost_tags,
    check_release_runs,
    check_running_vs_installed,
    check_symbols,
)
from scitex_dev.versioning._symbols import SymbolExpectation

from ._incident_data import (
    INCIDENT_GIT_TAGS,
    INCIDENT_PYPI_RELEASES,
    INCIDENT_RELEASE_RUNS,
)

UNIT = "scitex-dev.service"


# -- ghost-tag --------------------------------------------------------------


def test_head_ghost_tag_is_stale():
    # Arrange
    tags, released = INCIDENT_GIT_TAGS, INCIDENT_PYPI_RELEASES
    # Act
    finding = check_ghost_tags(tags, released)
    # Assert
    assert finding.state is Currency.STALE


def test_ghost_tag_names_the_unshipped_tag():
    # Arrange
    tags, released = INCIDENT_GIT_TAGS, INCIDENT_PYPI_RELEASES
    # Act
    finding = check_ghost_tags(tags, released)
    # Assert
    assert "v0.31.1" in finding.summary


def test_superseded_ghost_is_fresh():
    # Arrange — head tag published, an older tag never shipped.
    tags = ["v0.30.0", "v0.30.1", "v0.31.0"]
    released = {"0.30.0", "0.31.0"}  # 0.30.1 is a superseded ghost
    # Act
    finding = check_ghost_tags(tags, released)
    # Assert
    assert finding.state is Currency.FRESH


def test_ghost_tag_unknown_without_pypi():
    # Arrange
    tags = INCIDENT_GIT_TAGS
    # Act
    finding = check_ghost_tags(tags, None)
    # Assert
    assert finding.state is Currency.UNKNOWN


def test_ghost_tag_unknown_without_checkout():
    # Arrange
    released = INCIDENT_PYPI_RELEASES
    # Act
    finding = check_ghost_tags(None, released)
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- running-vs-installed ---------------------------------------------------


def test_daemon_older_than_install_is_stale():
    # Arrange — daemon up at t=1000, package written at t=5000.
    daemon, installed = 1_000.0, 5_000.0
    # Act
    finding = check_running_vs_installed(daemon, installed, unit=UNIT)
    # Assert
    assert finding.state is Currency.STALE


def test_daemon_restart_is_the_remedy():
    # Arrange
    daemon, installed = 1_000.0, 5_000.0
    # Act
    finding = check_running_vs_installed(daemon, installed, unit=UNIT)
    # Assert
    assert finding.remedy == f"systemctl --user restart {UNIT}"


def test_daemon_newer_than_install_is_fresh():
    # Arrange — package written at t=1000, daemon restarted at t=5000.
    daemon, installed = 5_000.0, 1_000.0
    # Act
    finding = check_running_vs_installed(daemon, installed, unit=UNIT)
    # Assert
    assert finding.state is Currency.FRESH


def test_daemon_not_running_is_unknown():
    # Arrange
    installed = 5_000.0
    # Act
    finding = check_running_vs_installed(None, installed, unit=UNIT)
    # Assert
    assert finding.state is Currency.UNKNOWN


def test_no_unit_configured_is_unknown():
    # Arrange
    daemon, installed = 1_000.0, 5_000.0
    # Act
    finding = check_running_vs_installed(daemon, installed, unit=None)
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- release-run ------------------------------------------------------------


def test_failed_release_run_is_stale():
    # Arrange
    runs = INCIDENT_RELEASE_RUNS
    # Act
    finding = check_release_runs(runs)
    # Assert
    assert finding.state is Currency.STALE


def test_successful_release_run_is_fresh():
    # Arrange
    runs = [{"conclusion": "success", "status": "completed", "headBranch": "v0.31.0"}]
    # Act
    finding = check_release_runs(runs)
    # Assert
    assert finding.state is Currency.FRESH


def test_cancelled_release_run_is_stale():
    # Arrange
    runs = [{"conclusion": "cancelled", "status": "completed", "headBranch": "v0.31.1"}]
    # Act
    finding = check_release_runs(runs)
    # Assert
    assert finding.state is Currency.STALE


def test_release_run_unknown_without_gh():
    # Arrange
    runs = None
    # Act
    finding = check_release_runs(runs)
    # Assert
    assert finding.state is Currency.UNKNOWN


def test_in_flight_run_is_not_judged():
    # Arrange
    runs = [{"status": "in_progress", "conclusion": None, "headBranch": "v9.9.9"}]
    # Act
    finding = check_release_runs(runs)
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- symbol-probe -----------------------------------------------------------


def test_present_symbol_is_fresh():
    # Arrange
    exp = SymbolExpectation(
        module="scitex_dev.versioning._symbols", symbol="probe", since="0.0.0", why="x"
    )
    # Act
    finding = check_symbols((exp,))
    # Assert
    assert finding.state is Currency.FRESH


def test_missing_symbol_is_stale():
    # Arrange
    exp = SymbolExpectation(
        module="scitex_dev.versioning._symbols", symbol="gone", since="9.9.9", why="x"
    )
    # Act
    finding = check_symbols((exp,))
    # Assert
    assert finding.state is Currency.STALE


def test_no_expectations_is_unknown():
    # Arrange
    expectations = ()
    # Act
    finding = check_symbols(expectations)
    # Assert
    assert finding.state is Currency.UNKNOWN


# EOF
