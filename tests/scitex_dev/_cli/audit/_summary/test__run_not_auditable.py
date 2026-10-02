# -*- coding: utf-8 -*-
"""Tests for the actionable `not-auditable` verdict (audit-cli).

When the grading interpreter lacks the subject's entry point, the
verdict must name the missing distribution, the interpreter that was
graded, AND the interpreter to use instead (the audited tree's own
`.venv` when `--path` names one) — "install it" is the wrong action
when the package is already installed one directory over.

No mocks — real `tmp_path` trees (a bare dir vs one with
`.venv/bin/python`). Single assert per test (PA-307).
"""

from __future__ import annotations

import sys
from pathlib import Path

from scitex_dev._cli.audit._summary._run import _no_entry_point_reason


def test_reason_names_the_missing_distribution(tmp_path: Path) -> None:
    # Arrange — a tree with no venv: only the generic remedy applies.
    # Act
    reason = _no_entry_point_reason("scitex-demo", tmp_path)
    # Assert
    assert "'scitex-demo'" in reason


def test_reason_names_the_grading_interpreter(tmp_path: Path) -> None:
    # Arrange
    # Act
    reason = _no_entry_point_reason("scitex-demo", tmp_path)
    # Assert
    assert sys.executable in reason


def test_tree_venv_is_named_as_the_remedy(tmp_path: Path) -> None:
    # Arrange — the audited tree ships its own venv, the overwhelmingly
    # likely home of the missing entry point.
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    # Act
    reason = _no_entry_point_reason("scitex-demo", tmp_path)
    # Assert
    assert str(venv_python) in reason


def test_tree_without_venv_falls_back_to_install_hint(
    tmp_path: Path,
) -> None:
    # Arrange — no own venv visible: say how to install instead.
    # Act
    reason = _no_entry_point_reason("scitex-demo", tmp_path)
    # Assert
    assert "pip install -e" in reason


def test_no_tree_falls_back_to_install_hint() -> None:
    # Arrange — no `--path` at all (registry mode): generic remedy.
    # Act
    reason = _no_entry_point_reason("scitex-demo")
    # Assert
    assert "pip install -e" in reason


# EOF
