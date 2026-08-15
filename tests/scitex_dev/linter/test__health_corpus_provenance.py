#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The rule corpus declares itself, so a stale verdict is visibly stale.

`describe_skips` returns [] when nothing was skipped, which means a run
that skips nothing says nothing about which corpus graded it. These tests
pin the opposite property for `describe_corpus`: it is NEVER empty.

The renderer is a pure function of a provenance dict, so the interesting
states — ambiguous, unknown, single — are exercised by passing real dicts
rather than by installing distributions or patching importlib.
"""

from __future__ import annotations

from scitex_dev.linter._health import corpus_provenance, describe_corpus


def _text(lines) -> str:
    return "\n".join(lines)


# -- the unconditional property ------------------------------------------
def test_a_single_version_still_produces_a_line():
    # Arrange — the healthy case must ALSO announce itself
    prov = {"versions": ["0.44.0"], "version": "0.44.0", "ambiguous": False,
            "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert lines != []


def test_the_healthy_line_names_the_version():
    # Arrange
    prov = {"versions": ["0.44.0"], "version": "0.44.0", "ambiguous": False,
            "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "0.44.0" in _text(lines)


def test_the_healthy_line_names_the_import_path():
    # Arrange — the version is metadata and metadata lies; the path does not
    prov = {"versions": ["0.44.0"], "version": "0.44.0", "ambiguous": False,
            "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "/x/scitex_dev/__init__.py" in _text(lines)


# -- two distributions claiming the package ------------------------------
def test_two_claiming_distributions_are_reported_as_ambiguous():
    # Arrange — measured on scitex-dev's own container, 2026-08-10
    prov = {"versions": ["0.38.0", "0.43.1"], "version": None,
            "ambiguous": True, "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "AMBIGUOUS" in _text(lines)


def test_an_ambiguous_corpus_lists_every_claimed_version():
    # Arrange — naming one of them would state a coin toss as fact
    prov = {"versions": ["0.38.0", "0.43.1"], "version": None,
            "ambiguous": True, "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "0.38.0, 0.43.1" in _text(lines)


def test_an_ambiguous_corpus_warns_that_one_reinstall_does_not_sweep():
    # Arrange — --force-reinstall removes only the resolved installation
    prov = {"versions": ["0.38.0", "0.43.1"], "version": None,
            "ambiguous": True, "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "does not sweep" in _text(lines)


# -- nothing claims the package ------------------------------------------
def test_no_claiming_distribution_reports_unknown_rather_than_guessing():
    # Arrange
    prov = {"versions": [], "version": None, "ambiguous": False,
            "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "UNKNOWN" in _text(lines)


def test_an_unknown_version_still_names_where_the_code_came_from():
    # Arrange — the path is recoverable even when the metadata is not
    prov = {"versions": [], "version": None, "ambiguous": False,
            "module_path": "/x/scitex_dev/__init__.py"}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "/x/scitex_dev/__init__.py" in _text(lines)


def test_a_missing_module_path_does_not_crash_the_renderer():
    # Arrange — a diagnostic that raises is worse than one that says less
    prov = {"versions": ["0.44.0"], "version": "0.44.0", "ambiguous": False,
            "module_path": None}
    # Act
    lines = describe_corpus(prov)
    # Assert
    assert "unknown path" in _text(lines)


# -- the live probe ------------------------------------------------------
def test_the_live_probe_reports_the_running_import_path():
    # Arrange — no argument means "read this interpreter"
    no_argument = None
    # Act
    prov = corpus_provenance() if no_argument is None else None
    # Assert
    assert "scitex_dev" in (prov["module_path"] or "")


def test_the_live_probe_is_renderable_without_arguments():
    # Arrange
    expected_empty: list[str] = []
    # Act
    lines = describe_corpus()
    # Assert
    assert lines != expected_empty

# EOF
