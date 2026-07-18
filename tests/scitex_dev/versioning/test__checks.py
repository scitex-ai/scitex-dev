#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install-currency DISPATCH — the safety of non-negotiable #2 lives here.

The headline test is ``test_editable_behind_metadata_but_current_tree_is_fresh``
(and its partner ``..._never_emits_pip_install_u``): an editable checkout whose
FROZEN metadata trails PyPI but whose working tree is current must resolve
FRESH by CONTENT and must NEVER be handed a ``pip install -U`` remedy — which
would clobber the checkout with a wheel. sac's ``check_host_behind_pypi``
would fail exactly this case, which is why it is deliberately NOT applied to
editable installs.
"""

from __future__ import annotations

from scitex_dev.versioning._checks import build_report, check_install_currency
from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._model import Currency
from scitex_dev.versioning._sources import StaticSources

CFG = VersioningConfig(dist="scitex-dev")


# -- wheel: the version compare is honest and DOES fire --------------------


def test_wheel_behind_pypi_is_stale():
    # Arrange
    kind, installed, latest = "wheel", "0.29.0", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=installed, metadata=installed,
        latest=latest, ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_wheel_behind_pypi_remedy_is_pip_install_u():
    # Arrange
    kind, installed, latest = "wheel", "0.29.0", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=installed, metadata=installed,
        latest=latest, ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.remedy == "/v/py -m pip install -U 'scitex-dev==0.31.0'"


def test_wheel_current_is_fresh():
    # Arrange
    kind, v = "wheel", "0.31.0"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=v, metadata=v, latest=v,
        ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.FRESH


# -- editable: the CONTENT probe, the dangerous compare is refused ----------


def test_editable_behind_metadata_but_current_tree_is_fresh():
    # Arrange — frozen metadata 0.21.21 trails PyPI 0.31.0, but the working
    # tree is 5 commits ahead of its own latest tag and 0 behind.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(5, 0), python="/v/py",
    )
    # Assert
    assert finding.state is Currency.FRESH


def test_editable_current_tree_never_emits_pip_install_u():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.31.0+dev", metadata="0.21.21",
        latest="0.31.0", ahead_behind=(5, 0), python="/v/py",
    )
    # Assert
    assert "pip install -U" not in finding.remedy


def test_editable_behind_its_tag_is_stale():
    # Arrange — working tree is 3 commits behind its latest release tag.
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), python="/v/py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_editable_behind_its_tag_remedy_is_git_pull_not_pip():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective="0.30.0", metadata="0.30.0",
        latest="0.31.0", ahead_behind=(0, 3), python="/v/py",
    )
    # Assert
    assert finding.remedy == "git pull"


def test_editable_without_checkout_is_unknown():
    # Arrange
    kind = "editable"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata="0.21.21",
        latest="0.31.0", ahead_behind=None, python="/v/py",
    )
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- orphaned: metadata with no code behind it -----------------------------


def test_orphaned_install_is_stale():
    # Arrange
    kind = "orphaned"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata="0.29.0",
        latest="0.31.0", ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.STALE


def test_absent_install_is_unknown():
    # Arrange
    kind = "absent"
    # Act
    finding = check_install_currency(
        kind, dist="scitex-dev", effective=None, metadata=None,
        latest="0.31.0", ahead_behind=None, python="py",
    )
    # Assert
    assert finding.state is Currency.UNKNOWN


# -- name-the-binary: every finding names WHO answered ---------------------


def test_every_finding_summary_names_the_binary():
    # Arrange — a source that reports its origin and interpreter.
    sources = StaticSources(
        install_kind="wheel",
        effective_version="0.31.0",
        metadata_version="0.31.0",
        module_origin="/opt/venv/lib/scitex_dev/__init__.py",
        executable="/opt/venv/bin/python3",
        pypi_latest="0.31.0",
    )
    # Act
    report = build_report(CFG, sources, now=1.0)
    tells_who = all(
        "/opt/venv/bin/python3" in f.summary and "scitex-dev @" in f.summary
        for f in report.findings
    )
    # Assert
    assert tells_who is True


def test_shadowed_old_install_origin_is_named():
    # Arrange — an OLD install shadowing from a repo .venv that predates use.
    sources = StaticSources(
        install_kind="wheel",
        effective_version="0.29.0",
        metadata_version="0.29.0",
        module_origin="/home/x/proj/old/.venv/lib/scitex_dev/__init__.py",
        executable="/home/x/proj/old/.venv/bin/python3",
        pypi_latest="0.31.0",
    )
    # Act
    report = build_report(CFG, sources, now=1.0)
    currency = report.findings[0]
    # Assert
    assert "/home/x/proj/old/.venv/lib/scitex_dev/__init__.py" in currency.summary


# -- aggregate: blind report is UNKNOWN, incident replay is STALE ----------


def test_blind_report_is_not_fresh():
    # Arrange — every source dark.
    sources = StaticSources()
    # Act
    report = build_report(CFG, sources, now=1.0)
    # Assert
    assert report.state is not Currency.FRESH


def test_blind_report_is_unknown():
    # Arrange
    sources = StaticSources()
    # Act
    report = build_report(CFG, sources, now=1.0)
    # Assert
    assert report.state is Currency.UNKNOWN


# EOF
