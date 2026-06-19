"""Tests for STX-HPC001 — SSH multiplexing disabled on the HPC path.

Forcing ``ControlMaster=no`` / ``ControlPath=none`` on SSH to a login node
opens a fresh connection per call — the pattern behind the Spartan admin
incident (2026-06-17, 440+ login-node connections). The rule must fire when a
source string literal carries either token, stay silent for the multiplexed
form, and honour the ``# stx-allow: STX-HPC001`` escape.
"""

from scitex_dev.linter.checker import lint_source


def _hpc001_ids(src, filepath="x.py"):
    return [
        i.rule.id
        for i in lint_source(src, filepath=filepath)
        if i.rule.id == "STX-HPC001"
    ]


def test_fires_on_control_master_no_in_arg_list():
    # Arrange
    src = 'cmd = ["ssh", "-o", "ControlMaster=no", "spartan"]'
    # Act
    ids = _hpc001_ids(src)
    # Assert
    assert ids == ["STX-HPC001"]


def test_fires_on_control_path_none():
    # Arrange
    src = 'opts = "-o ControlPath=none"'
    # Act
    ids = _hpc001_ids(src)
    # Assert
    assert ids == ["STX-HPC001"]


def test_fires_inside_fstring_literal_part():
    # Arrange — the literal chunk of an f-string is a Constant node.
    src = 'cmd = f"ssh -o ControlMaster=no {target} squeue"'
    # Act
    ids = _hpc001_ids(src)
    # Assert
    assert ids == ["STX-HPC001"]


def test_silent_on_multiplexed_form():
    # Arrange
    src = 'cmd = ["ssh", "-o", "ControlMaster=auto", "spartan"]'
    # Act
    ids = _hpc001_ids(src)
    # Assert
    assert ids == []


def test_stx_allow_comment_suppresses():
    # Arrange
    src = 'cmd = ["ssh", "-o", "ControlMaster=no"]  # stx-allow: STX-HPC001'
    # Act
    ids = _hpc001_ids(src)
    # Assert
    assert ids == []
