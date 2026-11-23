"""Full reports must retain integrity findings already carried by the matrix."""

import sys

import pytest

from scitex_dev._ecosystem._drift_report._build import render_report
from scitex_dev._ecosystem._drift_report._model import DriftMatrix
from scitex_dev._ecosystem._drift_report._package_watch import PackageDriftWarning
from scitex_dev._ecosystem._drift_report._untrustworthy_installs import (
    UntrustworthyInstallWarning,
)


def _integrity_warning():
    return UntrustworthyInstallWarning(
        package="owned-integrity-fixture",
        kind="orphaned",
        claimed="1.2.3",
        actual=None,
        detail="Owned model input: metadata without importable code.",
        hint="Owned diagnostic hint; no repair command is executed.",
    )


@pytest.mark.parametrize("field", ["package", "claimed", "hint"])
def test_full_report_retains_integrity_diagnostic(field):
    # Arrange
    warning = _integrity_warning()
    matrix = DriftMatrix(untrustworthy_installs=(warning,))
    expected = getattr(warning, field)
    # Act
    report = render_report(matrix)
    # Assert
    assert expected in report


@pytest.mark.parametrize("expected", ["UNTRUSTWORTHY INSTALL", sys.executable])
def test_full_report_identifies_integrity_warning_and_interpreter(expected):
    # Arrange
    matrix = DriftMatrix(untrustworthy_installs=(_integrity_warning(),))
    # Act
    report = render_report(matrix)
    # Assert
    assert expected in report


def test_integrity_warning_precedes_staleness_and_matrix():
    # Arrange
    stale = PackageDriftWarning("owned-stale-fixture", "1.0.0", "2.0.0", "pypi")
    matrix = DriftMatrix(
        package_drift_warnings=(stale,),
        untrustworthy_installs=(_integrity_warning(),),
    )
    # Act
    report = render_report(matrix)
    # Assert
    assert (
        0 <= report.find("UNTRUSTWORTHY INSTALL")
        < report.find("PACKAGE-DRIFT WARNING")
        < report.find("SciTeX ecosystem")
    )


def test_full_report_without_integrity_findings_has_no_integrity_banner():
    # Arrange
    matrix = DriftMatrix()
    # Act
    report = render_report(matrix)
    # Assert
    assert "UNTRUSTWORTHY INSTALL" not in report


def test_healthy_full_report_still_includes_matrix():
    # Arrange
    matrix = DriftMatrix()
    # Act
    report = render_report(matrix)
    # Assert
    assert "SciTeX ecosystem drift report" in report


def test_rendering_retains_json_findings():
    # Arrange
    matrix = DriftMatrix(untrustworthy_installs=(_integrity_warning(),))
    before = matrix.to_dict()
    # Act
    render_report(matrix)
    # Assert
    assert matrix.to_dict() == before


def test_rendering_retains_integrity_verdict():
    # Arrange
    matrix = DriftMatrix(untrustworthy_installs=(_integrity_warning(),))
    # Act
    render_report(matrix)
    # Assert
    assert matrix.has_drift
