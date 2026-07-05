#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the sac parse / fold / fail-open collection (`_sac.py`).

The ``sac versions --json`` verb is built in parallel and may not exist
yet, so these tests use synthetic fixtures of the exact
``{agent, layer, image, package, version, source}`` shape and injected
runners — no real subprocess, no mocks.
"""

from __future__ import annotations

import json

from scitex_dev._ecosystem._drift_report._sac import (
    collect_sac_rows,
    fold_sac_versions,
    parse_sac_output,
)


# A synthetic fixture of the exact verb shape (locked contract).
FIXTURE_ROWS = [
    {"agent": "a1", "layer": "base-image", "image": "img-a", "package": "scitex-io", "version": "1.0.0", "source": "manifest"},
    {"agent": "a1", "layer": "agent-overlay", "image": "img-a", "package": "scitex-io", "version": "1.1.0", "source": "live"},
    {"agent": "a2", "layer": "base-image", "image": "img-a", "package": "scitex-io", "version": "1.0.0", "source": "manifest"},
]


# ── parse_sac_output ─────────────────────────────────────────────────────────


def test_parse_sac_output_reads_bare_json_array():
    # Arrange
    text = json.dumps(FIXTURE_ROWS)
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows == FIXTURE_ROWS


def test_parse_sac_output_unwraps_versions_envelope():
    # Arrange
    text = json.dumps({"versions": FIXTURE_ROWS})
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows == FIXTURE_ROWS


def test_parse_sac_output_accepts_bytes():
    # Arrange
    raw = json.dumps(FIXTURE_ROWS).encode("utf-8")
    # Act
    rows = parse_sac_output(raw)
    # Assert
    assert rows == FIXTURE_ROWS


def test_parse_sac_output_empty_string_is_none():
    # Arrange
    text = "   "
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows is None


def test_parse_sac_output_invalid_json_is_none():
    # Arrange
    text = "not json {["
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows is None


def test_parse_sac_output_non_list_top_level_is_none():
    # Arrange
    text = json.dumps({"unexpected": "shape"})
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows is None


def test_parse_sac_output_drops_non_dict_rows():
    # Arrange
    text = json.dumps([{"package": "x", "version": "1", "layer": "base-image", "image": "i"}, 7, "bad"])
    # Act
    rows = parse_sac_output(text)
    # Assert
    assert rows == [{"package": "x", "version": "1", "layer": "base-image", "image": "i"}]


# ── fold_sac_versions ────────────────────────────────────────────────────────


def test_fold_sac_versions_indexes_base_by_image():
    # Arrange
    rows = FIXTURE_ROWS
    # Act
    fold = fold_sac_versions(rows)
    # Assert
    assert fold.base_by_image == {"img-a": {"scitex-io": "1.0.0"}}


def test_fold_sac_versions_indexes_overlay_by_agent():
    # Arrange
    rows = FIXTURE_ROWS
    # Act
    fold = fold_sac_versions(rows)
    # Assert
    assert fold.overlay_by_agent == {"a1": {"scitex-io": "1.1.0"}}


def test_fold_sac_versions_maps_agent_to_image():
    # Arrange
    rows = FIXTURE_ROWS
    # Act
    fold = fold_sac_versions(rows)
    # Assert
    assert fold.agent_image == {"a1": "img-a", "a2": "img-a"}


def test_fold_sac_versions_skips_rows_missing_package_or_version():
    # Arrange
    rows = [
        {"agent": "a", "layer": "base-image", "image": "i", "version": "1.0.0"},  # no package
        {"agent": "a", "layer": "base-image", "image": "i", "package": "p"},  # no version
        {"agent": "a", "layer": "base-image", "image": "i", "package": "p", "version": "2.0.0"},
    ]
    # Act
    fold = fold_sac_versions(rows)
    # Assert
    assert fold.base_by_image == {"i": {"p": "2.0.0"}}


def test_fold_sac_versions_none_input_yields_empty_fold():
    # Arrange
    rows = None
    # Act
    fold = fold_sac_versions(rows)
    # Assert
    assert fold.base_by_image == {} and fold.overlay_by_agent == {}


# ── collect_sac_rows — graceful degradation (no subprocess) ───────────────────


def test_collect_sac_rows_success_returns_rows_and_blank_note():
    # Arrange
    payload = json.dumps(FIXTURE_ROWS)

    def runner(argv):
        return (0, payload, "")

    # Act
    rows, note = collect_sac_rows(runner=runner)
    # Assert
    assert rows == FIXTURE_ROWS and note == ""


def test_collect_sac_rows_nonzero_exit_marks_verb_not_present():
    # Arrange
    def runner(argv):
        return (2, "", "No such command 'versions'")

    # Act
    rows, note = collect_sac_rows(runner=runner)
    # Assert
    assert rows is None and note == "unavailable (sac versions --json not present)"


def test_collect_sac_rows_runner_raising_degrades_gracefully():
    # Arrange
    def runner(argv):
        raise FileNotFoundError("sac")

    # Act
    rows, note = collect_sac_rows(runner=runner)
    # Assert
    assert rows is None and note.startswith("unavailable (sac versions --json failed")


def test_collect_sac_rows_unparseable_output_degrades_gracefully():
    # Arrange
    def runner(argv):
        return (0, "not-json", "")

    # Act
    rows, note = collect_sac_rows(runner=runner)
    # Assert
    assert rows is None and "not parseable" in note


def test_collect_sac_rows_absent_binary_reports_not_on_path():
    # Arrange
    def which(name):
        return None  # simulate `sac` not installed

    # Act
    rows, note = collect_sac_rows(which=which)
    # Assert
    assert rows is None and note == "unavailable (sac not on PATH)"
