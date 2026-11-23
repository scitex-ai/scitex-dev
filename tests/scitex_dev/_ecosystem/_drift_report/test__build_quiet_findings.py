"""Quiet reports retain counts for each existing non-clean finding category."""

from scitex_dev._ecosystem._drift_report._build import render_quiet
from scitex_dev._ecosystem._drift_report._model import (
    DriftMatrix,
    LayerCell,
    PackageDrift,
)
from scitex_dev._ecosystem._drift_report._package_watch import PackageDriftWarning
from scitex_dev._ecosystem._drift_report._untrustworthy_installs import (
    UntrustworthyInstallWarning,
)


def _warning(package="owned-integrity"):
    return UntrustworthyInstallWarning(package, "orphaned", "1.0.0", None, "owned", None)


def test_quiet_counts_missing_reference_rows():
    # Arrange
    matrix = DriftMatrix(packages=(PackageDrift("owned-missing", None, None),))
    # Act
    report = render_quiet(matrix)
    # Assert
    assert "1 NOT JUDGEABLE" in report


def test_quiet_counts_integrity_findings():
    # Arrange
    matrix = DriftMatrix(untrustworthy_installs=(_warning(),))
    # Act
    report = render_quiet(matrix)
    # Assert
    assert "1 untrustworthy install(s)" in report


def test_quiet_keeps_all_finding_categories_distinct():
    # Arrange
    matrix = DriftMatrix(
        packages=(
            PackageDrift("owned-clean", "1.0.0", None),
            PackageDrift(
                "owned-drift", "1.0.0", None,
                cells=(LayerCell("pypi", "2.0.0", "version", True),),
            ),
            PackageDrift("owned-missing", None, None),
        ),
        sac_available=True,
        package_drift_warnings=(PackageDriftWarning("owned-stale", "1", "2", "pypi"),),
        untrustworthy_installs=(_warning("owned-first"), _warning("owned-second")),
    )
    # Act
    report = render_quiet(matrix)
    # Assert
    assert report == (
        "drift: 1/3 packages consistent; 1 drifting; 1 NOT JUDGEABLE; "
        "1 critical package(s) behind fleet-current; 2 untrustworthy install(s)"
    )


def test_quiet_preserves_consistent_only_output():
    # Arrange
    matrix = DriftMatrix(
        packages=(PackageDrift("owned-clean", "1.0.0", None),), sac_available=True
    )
    # Act
    report = render_quiet(matrix)
    # Assert
    assert report == "drift: 1/1 packages consistent; 0 drifting"


def test_quiet_preserves_unavailable_container_note():
    # Arrange
    matrix = DriftMatrix()
    # Act
    report = render_quiet(matrix)
    # Assert
    assert report == (
        "drift: 0/0 packages consistent; 0 drifting (sac layers 5/6 unavailable)"
    )


def test_quiet_does_not_mutate_json_findings():
    # Arrange
    matrix = DriftMatrix(untrustworthy_installs=(_warning(),))
    before = matrix.to_dict()
    # Act
    render_quiet(matrix)
    # Assert
    assert matrix.to_dict() == before
