"""Structured row counts expose missing baselines without treating them as drift."""

import pytest

from scitex_dev._ecosystem._drift_report._model import (
    DriftMatrix,
    LayerCell,
    PackageDrift,
)


def _row(kind, index):
    name = f"owned-summary-{index}"
    if kind == "unknown":
        return PackageDrift(name, None, None)
    cells = (LayerCell("pypi", "2.0.0", "version", True),) if kind == "drift" else ()
    return PackageDrift(name, "1.0.0", None, cells=cells)


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        ((), (0, 0, 0, 0)),
        (("clean",), (1, 1, 0, 0)),
        (("drift",), (1, 0, 1, 0)),
        (("unknown",), (1, 0, 0, 1)),
        (("unknown", "unknown"), (2, 0, 0, 2)),
        (("clean", "drift", "unknown"), (3, 1, 1, 1)),
    ],
)
def test_summary_reports_each_row_state(kinds, expected):
    # Arrange
    matrix = DriftMatrix(packages=tuple(_row(kind, i) for i, kind in enumerate(kinds)))
    fields = ("total", "consistent", "drifting", "unjudgeable")
    # Act
    summary = matrix.to_dict()["summary"]
    # Assert
    assert summary == dict(zip(fields, expected))


def test_summary_retains_existing_three_counts():
    # Arrange
    kinds = ("clean", "drift", "unknown")
    matrix = DriftMatrix(packages=tuple(_row(kind, i) for i, kind in enumerate(kinds)))
    # Act
    summary = matrix.to_dict()["summary"]
    # Assert
    assert {field: summary[field] for field in ("total", "consistent", "drifting")} == {
        "total": 3, "consistent": 1, "drifting": 1
    }
