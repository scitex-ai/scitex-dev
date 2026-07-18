#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end ``check_currency`` — the two headline guarantees, on recorded data.

1. THE INCIDENT REGRESSION (``test_would_have_caught_the_incident``): replays a
   host on an older wheel while a newer version shipped AND the head tag never
   published. The verdict MUST be STALE. If this ever reads FRESH, the alarm is
   worthless — this is the whole reason the primitive exists.

2. THE NEGATIVE TEST (non-negotiable #2): a fully-current EDITABLE box whose
   only "problem" is that its frozen metadata trails PyPI must resolve FRESH,
   and NO finding anywhere may carry a ``pip install -U`` remedy.

Driven through ``StaticSources`` — a real implementation of the ``Sources``
protocol fed recorded evidence. No network, no mocks.

Named ``test___init__.py`` rather than ``test_check_currency.py``: PS-204
mirrors test files onto src MODULES, and ``check_currency`` is defined in
``versioning/__init__.py`` — there is no ``check_currency.py`` to mirror.
"""

from __future__ import annotations

from scitex_dev.versioning import check_currency
from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._model import Currency
from scitex_dev.versioning._sources import StaticSources
from scitex_dev.versioning._symbols import SymbolExpectation

from ._incident_data import (
    INCIDENT_GIT_TAGS,
    INCIDENT_INSTALLED,
    INCIDENT_PYPI_LATEST,
    INCIDENT_PYPI_RELEASES,
    INCIDENT_RELEASE_RUNS,
)

# A symbol that genuinely exists in this checkout, so the symbol-probe check
# resolves FRESH here (rather than UNKNOWN for an empty registry) — the
# fully-current negative-test box must aggregate to FRESH end to end.
_PRESENT = SymbolExpectation(
    module="scitex_dev.versioning._symbols", symbol="probe", since="0.0.0", why="probe fn"
)
CFG = VersioningConfig(
    dist="scitex-dev", systemd_unit="scitex-dev.service", expectations=(_PRESENT,)
)


def test_would_have_caught_the_incident():
    # Arrange — host on an old wheel, head tag v0.31.1 never shipped.
    sources = StaticSources(
        install_kind="wheel",
        effective_version=INCIDENT_INSTALLED,
        metadata_version=INCIDENT_INSTALLED,
        module_origin="/opt/venv/lib/scitex_dev/__init__.py",
        executable="/opt/venv/bin/python3",
        pypi_latest=INCIDENT_PYPI_LATEST,
        pypi_versions=INCIDENT_PYPI_RELEASES,
        git_tags=INCIDENT_GIT_TAGS,
        release_runs=INCIDENT_RELEASE_RUNS,
        installed_at=5_000.0,
        daemon_started_at=1_000.0,
    )
    # Act
    report = check_currency(CFG, sources, now=1.0)
    # Assert
    assert report.state is Currency.STALE


def test_incident_report_names_the_binary_in_a_stale_finding():
    # Arrange
    sources = StaticSources(
        install_kind="wheel",
        effective_version=INCIDENT_INSTALLED,
        metadata_version=INCIDENT_INSTALLED,
        module_origin="/opt/venv/lib/scitex_dev/__init__.py",
        executable="/opt/venv/bin/python3",
        pypi_latest=INCIDENT_PYPI_LATEST,
        pypi_versions=INCIDENT_PYPI_RELEASES,
        git_tags=INCIDENT_GIT_TAGS,
        release_runs=INCIDENT_RELEASE_RUNS,
    )
    # Act
    report = check_currency(CFG, sources, now=1.0)
    named = all("/opt/venv/bin/python3" in f.summary for f in report.stale)
    # Assert
    assert named is True


def _fully_current_editable_but_fossil_metadata() -> StaticSources:
    """Editable box: working tree current, tags all published, run green,
    daemon fresh — the ONLY anomaly is the fossil metadata trailing PyPI."""
    return StaticSources(
        install_kind="editable",
        effective_version="0.31.0+dev",
        metadata_version="0.21.21",  # the fossil, far behind PyPI
        module_origin="/home/dev/proj/scitex-dev/src/scitex_dev/__init__.py",
        executable="/home/dev/proj/scitex-dev/.venv/bin/python3",
        pypi_latest="0.31.0",
        pypi_versions={"0.30.0", "0.30.1", "0.31.0"},
        git_tags=["v0.30.0", "v0.30.1", "v0.31.0"],
        editable_ahead_behind=(4, 0),  # ahead of its tag, 0 behind
        release_runs=[{"conclusion": "success", "status": "completed", "headBranch": "v0.31.0"}],
        installed_at=1_000.0,
        daemon_started_at=5_000.0,  # daemon restarted AFTER install
    )


def test_editable_with_fossil_metadata_resolves_fresh():
    # Arrange
    sources = _fully_current_editable_but_fossil_metadata()
    # Act
    report = check_currency(CFG, sources, now=1.0)
    # Assert
    assert report.state is Currency.FRESH


def test_editable_with_fossil_metadata_never_emits_pip_install_u():
    # Arrange
    sources = _fully_current_editable_but_fossil_metadata()
    # Act
    report = check_currency(CFG, sources, now=1.0)
    offending = [f for f in report.findings if "pip install -U" in f.remedy]
    # Assert
    assert offending == []


# EOF
