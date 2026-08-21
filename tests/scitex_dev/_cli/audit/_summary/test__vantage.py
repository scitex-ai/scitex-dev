#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The audit must name the artifact it measured.

No mocks (STX-NM002): every test builds a real Click command and drives the
real `resolved_vantage`, so the reported provenance comes from the same code
path the audit uses. Nothing patches importlib or fakes a module.

Context: on 2026-08-21 two agents disagreed for an evening over 24 findings.
Both were correct about DIFFERENT trees, reached through a `PYTHONPATH` that
pointed one of them at a worktree. Both trees reported version `0.48.0`, so
only the resolved `__file__` could have distinguished them. These tests pin
the two properties that would have ended it: a path is reported, and it is
the AUDITED package's path rather than the framework's.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click  # noqa: E402

from scitex_dev._cli.audit._summary._vantage import (  # noqa: E402
    UNRESOLVED,
    alignment,
    format_alignment,
    format_vantage,
    resolved_vantage,
)

_ABSENT = "definitely-not-an-installed-console-script-xyz"


@click.command()
def _demo():
    """A real Click leaf defined in THIS module."""


@click.group()
def _demo_group():
    """A real Click group defined in THIS module."""


def test_vantage_reports_the_file_of_the_module_that_defined_the_command():
    """The load-bearing field: which file on disk produced this object."""
    # Arrange
    root = _demo
    # Act
    vantage = resolved_vantage(_ABSENT, root=root)
    # Assert
    assert vantage["module_file"].endswith("test__vantage.py")


def test_vantage_never_reports_clicks_own_module_for_a_command():
    """`Command.__module__` is `click.core`; reporting it would be a wrong
    path that reads like a right one."""
    # Arrange
    root = _demo
    # Act
    vantage = resolved_vantage(_ABSENT, root=root)
    # Assert
    assert vantage["module"].split(".")[0] != "click"


def test_vantage_never_reports_clicks_own_module_for_a_group():
    """Groups are instances too, and take the same fallback."""
    # Arrange
    root = _demo_group
    # Act
    vantage = resolved_vantage(_ABSENT, root=root)
    # Assert
    assert vantage["module"].split(".")[0] != "click"


def test_unresolvable_field_is_named_rather_than_blank():
    """A blank renders as a real (empty) answer; the sentinel cannot."""
    # Arrange
    package = _ABSENT
    # Act
    vantage = resolved_vantage(package)
    # Assert
    assert vantage["module_file"] == UNRESOLVED


def test_the_sentinel_is_not_falsy():
    """`if not vantage[...]` must not silently treat unknown as absent."""
    # Arrange
    sentinel = UNRESOLVED
    # Act
    truthiness = bool(sentinel)
    # Assert
    assert truthiness is True


def test_rendered_line_carries_the_path():
    """Version alone is NOT identifying — two trees reported 0.48.0 with
    different files. The path must survive into the human output."""
    # Arrange
    vantage = resolved_vantage(_ABSENT, root=_demo)
    # Act
    line = format_vantage(vantage)
    # Assert
    assert "test__vantage.py" in line


def test_rendered_line_tolerates_a_vantage_missing_every_key():
    """The report must never raise while explaining a failure."""
    # Arrange
    empty: dict[str, str] = {}
    # Act
    line = format_vantage(empty)
    # Assert
    assert UNRESOLVED in line


def test_files_and_objects_from_one_tree_report_aligned():
    """The ordinary case: the imported module lives under the audited path."""
    # Arrange
    vantage = {"module_file": "/repo/src/pkg/__init__.py"}
    # Act
    state = alignment(vantage, "/repo")
    # Assert
    assert state == "aligned"


def test_files_and_objects_from_different_trees_report_mismatch():
    """The hybrid: --path names one tree, the interpreter imported another."""
    # Arrange
    vantage = {"module_file": "/elsewhere/site-packages/pkg/__init__.py"}
    # Act
    state = alignment(vantage, "/repo")
    # Assert
    assert state == "mismatch"


def test_no_audited_path_reports_unknown_not_aligned():
    """With nothing to compare, 'aligned' would be a fabricated reassurance."""
    # Arrange
    vantage = {"module_file": "/repo/src/pkg/__init__.py"}
    # Act
    state = alignment(vantage, None)
    # Assert
    assert state == "unknown"


def test_unresolved_module_file_reports_unknown_not_aligned():
    """An unresolved path cannot be judged against anything."""
    # Arrange
    vantage = {"module_file": UNRESOLVED}
    # Act
    state = alignment(vantage, "/repo")
    # Assert
    assert state == "unknown"


def test_mismatch_warning_names_the_imported_tree():
    """The reader must see WHICH tree the CLI findings actually describe."""
    # Arrange
    vantage = {"module_file": "/elsewhere/site-packages/pkg/__init__.py"}
    # Act
    warning = format_alignment(vantage, "/repo")
    # Assert
    assert "/elsewhere/site-packages/pkg/__init__.py" in warning


def test_aligned_run_emits_no_warning_line():
    """A warning that prints on every run stops being read."""
    # Arrange
    vantage = {"module_file": "/repo/src/pkg/__init__.py"}
    # Act
    warning = format_alignment(vantage, "/repo")
    # Assert
    assert warning is None


def test_alignment_ignores_a_matching_version_and_compares_paths():
    """The incident case: both trees reported 0.48.0 across a 23-error gap.

    A version comparison would have stayed silent. Only the path separates
    them, so a matching version must not soften the verdict.
    """
    # Arrange
    vantage = {
        "module_file": "/elsewhere/site-packages/pkg/__init__.py",
        "distribution_version": "0.48.0",
    }
    # Act
    state = alignment(vantage, "/repo")
    # Assert
    assert state == "mismatch"
