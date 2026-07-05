#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for matrix assembly + drift classification + rendering (`_build.py`).

All pure — synthetic per-package input dicts, no network / subprocess /
mocks. Mirrors ``_packages.py``'s injected-data test style.
"""

from __future__ import annotations

from scitex_dev._ecosystem._drift_report._build import (
    _classify_version,
    _representative_version_cell,
    _sha_drift,
    build_drift_matrix,
    render_matrix,
    render_quiet,
    render_report,
)
from scitex_dev._ecosystem._drift_report._model import (
    KIND_NA,
    LAYER_AGENT_OVERLAY,
    LAYER_BASE_IMAGE,
    LAYER_CI,
    LAYER_EDITABLE,
    LAYER_PYPI,
)

SHA_OK = "a" * 40
SHA_OTHER = "b" * 40


def _inputs(**over):
    """Default all-consistent inputs for one package/one host; overridable."""
    base = dict(
        packages=["scitex-io"],
        hosts=["spartan"],
        reference_versions={"scitex-io": "1.0.0"},
        installed_versions={"scitex-io": "1.0.0"},
        pypi_versions={"scitex-io": "1.0.0"},
        tag_versions={"scitex-io": "1.0.0"},
        sha_rows=[
            {
                "pkg": "scitex-io",
                "origin": SHA_OK,
                "localhost": SHA_OK,
                "cells": {"spartan": SHA_OK},
            }
        ],
        pypi_names={"scitex-io": "scitex-io"},
        sac_rows=[],
        sac_note="",
    )
    base.update(over)
    return base


# ── _classify_version ────────────────────────────────────────────────────────


def test_classify_version_equal_is_not_drift():
    # Arrange
    value, reference = "1.0.0", "1.0.0"
    # Act
    drift, note = _classify_version(value, reference)
    # Assert
    assert drift is False and note == ""


def test_classify_version_behind_is_drift_with_note():
    # Arrange
    value, reference = "0.9.0", "1.0.0"
    # Act
    drift, note = _classify_version(value, reference)
    # Assert
    assert drift is True and note == "behind SSoT"


def test_classify_version_ahead_is_drift_with_note():
    # Arrange
    value, reference = "1.1.0", "1.0.0"
    # Act
    drift, note = _classify_version(value, reference)
    # Assert
    assert drift is True and note == "ahead of SSoT"


def test_classify_version_unknown_value_is_not_drift():
    # Arrange
    value, reference = None, "1.0.0"
    # Act
    drift, note = _classify_version(value, reference)
    # Assert
    assert drift is False


def test_classify_version_missing_reference_is_not_drift():
    # Arrange
    value, reference = "1.0.0", None
    # Act
    drift, note = _classify_version(value, reference)
    # Assert
    assert drift is False and note == "no SSoT reference"


# ── _sha_drift ───────────────────────────────────────────────────────────────


def test_sha_drift_true_when_known_shas_differ():
    # Arrange
    value, reference = SHA_OTHER, SHA_OK
    # Act
    drift = _sha_drift(value, reference)
    # Assert
    assert drift is True


def test_sha_drift_false_when_shas_match():
    # Arrange
    value, reference = SHA_OK, SHA_OK
    # Act
    drift = _sha_drift(value, reference)
    # Assert
    assert drift is False


def test_sha_drift_excluded_or_none_is_not_drift():
    # Arrange
    sentinels = ["EXCLUDED", None, "ERROR"]
    # Act
    drifts = [_sha_drift(s, SHA_OK) for s in sentinels]
    # Assert
    assert drifts == [False, False, False]


# ── _representative_version_cell ─────────────────────────────────────────────


def test_representative_empty_is_unknown_na_cell():
    # Arrange
    versions = {}
    # Act
    cell = _representative_version_cell(LAYER_BASE_IMAGE, versions, "1.0.0")
    # Assert
    assert cell.value is None and cell.kind == KIND_NA and cell.drift is False


def test_representative_single_matching_version_no_drift():
    # Arrange
    versions = {"img-a": "1.0.0"}
    # Act
    cell = _representative_version_cell(LAYER_BASE_IMAGE, versions, "1.0.0")
    # Assert
    assert cell.value == "1.0.0" and cell.drift is False


def test_representative_mixed_versions_flag_drift_with_breakdown():
    # Arrange
    versions = {"img-a": "1.0.0", "img-b": "0.9.0"}
    # Act
    cell = _representative_version_cell(LAYER_BASE_IMAGE, versions, "1.0.0")
    # Assert
    assert cell.value == "mixed" and cell.drift is True and "img-b=0.9.0" in cell.note


# ── build_drift_matrix — end to end ──────────────────────────────────────────


def test_build_matrix_all_consistent_has_no_drift():
    # Arrange
    inputs = _inputs()
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    assert matrix.has_drift is False and len(matrix.consistent_packages) == 1


def test_build_matrix_pypi_behind_ssot_is_flagged():
    # Arrange
    inputs = _inputs(pypi_versions={"scitex-io": "0.9.0"})
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    row = matrix.packages[0]
    assert row.cell(LAYER_PYPI).drift is True and LAYER_PYPI in row.drifting_layers


def test_build_matrix_host_sha_mismatch_is_flagged():
    # Arrange
    sha_rows = [
        {"pkg": "scitex-io", "origin": SHA_OK, "localhost": SHA_OK, "cells": {"spartan": SHA_OTHER}}
    ]
    inputs = _inputs(sha_rows=sha_rows)
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    assert matrix.packages[0].cell("host:spartan").drift is True


def test_build_matrix_unreachable_host_is_unknown_not_drift():
    # Arrange
    sha_rows = [
        {"pkg": "scitex-io", "origin": SHA_OK, "localhost": SHA_OK, "cells": {"spartan": None}}
    ]
    inputs = _inputs(sha_rows=sha_rows)
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert — a down host degrades gracefully, never trips the gate
    cell = matrix.packages[0].cell("host:spartan")
    assert cell.drift is False and cell.value is None and matrix.has_drift is False


def test_build_matrix_editable_installed_mismatch_is_flagged():
    # Arrange
    inputs = _inputs(installed_versions={"scitex-io": "0.9.0"})
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    assert matrix.packages[0].cell(LAYER_EDITABLE).drift is True


def test_build_matrix_ci_layer_is_always_not_collected():
    # Arrange
    inputs = _inputs()
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert — CI is honestly not-collected, never faked, never drift
    ci = matrix.packages[0].cell(LAYER_CI)
    assert ci.kind == KIND_NA and ci.drift is False and "not-collected" in ci.note


def test_build_matrix_folds_sac_base_and_overlay_layers():
    # Arrange
    sac_rows = [
        {"agent": "a1", "layer": "base-image", "image": "img", "package": "scitex-io", "version": "1.0.0"},
        {"agent": "a1", "layer": "agent-overlay", "image": "img", "package": "scitex-io", "version": "1.0.0"},
    ]
    inputs = _inputs(sac_rows=sac_rows)
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    row = matrix.packages[0]
    assert row.cell(LAYER_BASE_IMAGE).value == "1.0.0" and row.cell(LAYER_AGENT_OVERLAY).value == "1.0.0"


def test_build_matrix_sac_overlay_behind_ssot_is_flagged():
    # Arrange
    sac_rows = [
        {"agent": "a1", "layer": "base-image", "image": "img", "package": "scitex-io", "version": "1.0.0"},
        {"agent": "a1", "layer": "agent-overlay", "image": "img", "package": "scitex-io", "version": "0.9.0"},
    ]
    inputs = _inputs(sac_rows=sac_rows)
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert — the overlay effective version (0.9.0) trails the SSoT
    assert matrix.packages[0].cell(LAYER_AGENT_OVERLAY).drift is True


def test_build_matrix_sac_absent_marks_availability_false():
    # Arrange
    inputs = _inputs(sac_rows=None, sac_note="unavailable (sac versions --json not present)")
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    assert matrix.sac_available is False


def test_build_matrix_sac_absent_layers_na_and_no_false_drift():
    # Arrange
    inputs = _inputs(sac_rows=None, sac_note="unavailable (sac versions --json not present)")
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert — graceful degradation: layers 5/6 unknown, no false drift
    row = matrix.packages[0]
    assert (
        row.cell(LAYER_BASE_IMAGE).kind == KIND_NA
        and row.cell(LAYER_AGENT_OVERLAY).drift is False
        and matrix.has_drift is False
    )


def test_build_matrix_layers_include_host_columns_in_order():
    # Arrange
    inputs = _inputs(hosts=["ywata-note-win", "spartan"])
    # Act
    matrix = build_drift_matrix(**inputs)
    # Assert
    assert (
        matrix.layers[0] == LAYER_PYPI
        and "host:ywata-note-win" in matrix.layers
        and "host:spartan" in matrix.layers
    )


# ── rendering ────────────────────────────────────────────────────────────────


def test_render_matrix_has_header_and_package_row():
    # Arrange
    matrix = build_drift_matrix(**_inputs())
    # Act
    text = render_matrix(matrix)
    # Assert
    assert "pkg" in text.splitlines()[0] and "scitex-io" in text


def test_render_report_marks_drift_and_lists_detail():
    # Arrange
    matrix = build_drift_matrix(**_inputs(pypi_versions={"scitex-io": "0.9.0"}))
    # Act
    text = render_report(matrix)
    # Assert — the drifting cell carries a `*` and a per-package detail line
    assert "0.9.0*" in text and "drift detail" in text


def test_render_report_notes_sac_unavailable_footnote():
    # Arrange
    matrix = build_drift_matrix(
        **_inputs(sac_rows=None, sac_note="unavailable (sac versions --json not present)")
    )
    # Act
    text = render_report(matrix)
    # Assert
    assert "sac versions --json not present" in text


def test_render_quiet_summarizes_consistency_counts():
    # Arrange
    matrix = build_drift_matrix(**_inputs(pypi_versions={"scitex-io": "0.9.0"}))
    # Act
    line = render_quiet(matrix)
    # Assert
    assert "1 drifting" in line
