#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the drift-report value objects (`_model.py`).

Pure dataclasses — no network / subprocess / mocks.
"""

from __future__ import annotations

from scitex_dev._ecosystem._drift_report._model import (
    KIND_NA,
    KIND_SHA,
    KIND_VERSION,
    DriftMatrix,
    LayerCell,
    PackageDrift,
    SacFold,
)


# ── LayerCell ────────────────────────────────────────────────────────────────


def test_layer_cell_to_dict_round_trips_fields():
    # Arrange
    cell = LayerCell("pypi", "1.2.3", KIND_VERSION, True, "behind SSoT")
    # Act
    d = cell.to_dict()
    # Assert
    assert d == {
        "layer": "pypi",
        "value": "1.2.3",
        "kind": KIND_VERSION,
        "drift": True,
        "note": "behind SSoT",
    }


# ── PackageDrift ─────────────────────────────────────────────────────────────


def _row(cells):
    return PackageDrift(
        pkg="scitex-io", reference_version="1.0.0", reference_sha="a" * 40, cells=cells
    )


def test_package_drift_drifting_layers_lists_only_drifting_cells():
    # Arrange
    row = _row(
        (
            LayerCell("pypi", "0.9.0", KIND_VERSION, True, ""),
            LayerCell("editable", "1.0.0", KIND_VERSION, False, ""),
        )
    )
    # Act
    layers = row.drifting_layers
    # Assert
    assert layers == ["pypi"]


def test_package_drift_consistent_true_when_no_cell_drifts():
    # Arrange
    row = _row((LayerCell("editable", "1.0.0", KIND_VERSION, False, ""),))
    # Act
    consistent = row.consistent
    # Assert
    assert consistent is True


def test_package_drift_consistent_false_when_any_cell_drifts():
    # Arrange
    row = _row((LayerCell("pypi", "0.9.0", KIND_VERSION, True, ""),))
    # Act
    consistent = row.consistent
    # Assert
    assert consistent is False


def test_package_drift_cell_lookup_returns_matching_layer():
    # Arrange
    target = LayerCell("host:spartan", "abc1234", KIND_SHA, False, "")
    row = _row((target,))
    # Act
    found = row.cell("host:spartan")
    # Assert
    assert found is target


def test_package_drift_cell_lookup_missing_returns_none():
    # Arrange
    row = _row((LayerCell("pypi", "1.0.0", KIND_VERSION, False, ""),))
    # Act
    found = row.cell("ci")
    # Assert
    assert found is None


def test_package_drift_to_dict_exposes_consistency_summary():
    # Arrange
    row = _row((LayerCell("pypi", "0.9.0", KIND_VERSION, True, "behind SSoT"),))
    # Act
    d = row.to_dict()
    # Assert
    assert d["consistent"] is False and d["drifting_layers"] == ["pypi"]


# ── DriftMatrix ──────────────────────────────────────────────────────────────


def _matrix(rows, **kw):
    return DriftMatrix(packages=rows, layers=("pypi",), hosts=(), **kw)


def test_drift_matrix_partitions_drifting_and_consistent():
    # Arrange
    ok = PackageDrift("a", "1.0.0", None, (LayerCell("pypi", "1.0.0", KIND_VERSION, False, ""),))
    bad = PackageDrift("b", "1.0.0", None, (LayerCell("pypi", "0.9.0", KIND_VERSION, True, ""),))
    matrix = _matrix((ok, bad))
    # Act
    drifting = [p.pkg for p in matrix.drifting]
    consistent = [p.pkg for p in matrix.consistent_packages]
    # Assert
    assert drifting == ["b"] and consistent == ["a"]


def test_drift_matrix_has_drift_true_when_any_package_drifts():
    # Arrange
    bad = PackageDrift("b", "1.0.0", None, (LayerCell("pypi", "0.9.0", KIND_VERSION, True, ""),))
    matrix = _matrix((bad,))
    # Act
    has_drift = matrix.has_drift
    # Assert
    assert has_drift is True


def test_drift_matrix_has_drift_false_when_all_consistent():
    # Arrange
    ok = PackageDrift("a", "1.0.0", None, (LayerCell("pypi", "1.0.0", KIND_VERSION, False, ""),))
    matrix = _matrix((ok,))
    # Act
    has_drift = matrix.has_drift
    # Assert
    assert has_drift is False


def test_drift_matrix_to_dict_summary_counts():
    # Arrange
    ok = PackageDrift("a", "1.0.0", None, (LayerCell("pypi", "1.0.0", KIND_VERSION, False, ""),))
    bad = PackageDrift("b", "1.0.0", None, (LayerCell("pypi", "0.9.0", KIND_VERSION, True, ""),))
    matrix = _matrix((ok, bad), sac_available=False, sac_note="unavailable (sac not on PATH)")
    # Act
    d = matrix.to_dict()
    # Assert
    assert d["summary"] == {"total": 2, "consistent": 1, "drifting": 1}


def test_drift_matrix_to_dict_carries_sac_availability():
    # Arrange
    matrix = _matrix((), sac_available=False, sac_note="unavailable (sac not on PATH)")
    # Act
    d = matrix.to_dict()
    # Assert
    assert d["sac_available"] is False and "sac not on PATH" in d["sac_note"]


# ── SacFold — overlay-else-base effective resolution ─────────────────────────


def _fold():
    return SacFold(
        base_by_image={"img-a": {"scitex-io": "1.0.0", "scitex-plt": "2.0.0"}},
        overlay_by_agent={"agent-x": {"scitex-io": "1.1.0"}},
        agent_image={"agent-x": "img-a", "agent-y": "img-a"},
    )


def test_sac_fold_effective_prefers_agent_overlay():
    # Arrange
    fold = _fold()
    # Act
    version = fold.effective("agent-x", "scitex-io")
    # Assert — agent-x overrides scitex-io in its overlay
    assert version == "1.1.0"


def test_sac_fold_effective_falls_back_to_base_image():
    # Arrange
    fold = _fold()
    # Act
    version = fold.effective("agent-y", "scitex-io")
    # Assert — agent-y has no overlay → base image version
    assert version == "1.0.0"


def test_sac_fold_effective_unknown_agent_is_none():
    # Arrange
    fold = _fold()
    # Act
    version = fold.effective("ghost", "scitex-io")
    # Assert
    assert version is None


def test_sac_fold_base_versions_for_maps_image_to_version():
    # Arrange
    fold = _fold()
    # Act
    versions = fold.base_versions_for("scitex-plt")
    # Assert
    assert versions == {"img-a": "2.0.0"}


def test_sac_fold_effective_versions_for_covers_all_agents():
    # Arrange
    fold = _fold()
    # Act
    eff = fold.effective_versions_for("scitex-io")
    # Assert — agent-x overlay (1.1.0), agent-y base (1.0.0)
    assert eff == {"agent-x": "1.1.0", "agent-y": "1.0.0"}


def test_kind_na_constant_distinct_from_version_and_sha():
    # Arrange
    kinds = {KIND_NA, KIND_VERSION, KIND_SHA}
    # Act
    distinct = len(kinds)
    # Assert
    assert distinct == 3
