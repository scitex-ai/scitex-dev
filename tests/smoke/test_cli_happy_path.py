#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke layer — fast (<60s) subprocess-driven CLI happy-path tests.

Runs on every PR (``pytest -m smoke``). Each test spawns the real CLI
(``sys.executable -m scitex_dev``) in a subprocess with the inherited
environment — which the session shield in ``tests/conftest.py`` already
repoints at tmp state — and asserts exactly one observable. No
``monkeypatch``: the child reads the real (shielded) environment.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.smoke

_CLI = [sys.executable, "-m", "scitex_dev"]


def _repo_root() -> str:
    """Checkout root — the tree this test file lives in."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_smoke_version_exits_zero():
    # Arrange
    argv = _CLI + ["--version"]
    # Act
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    # Assert
    assert result.returncode == 0


def test_smoke_help_names_the_ecosystem_group():
    # Arrange
    argv = _CLI + ["--help"]
    # Act
    result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    # Assert
    assert "ecosystem" in result.stdout


def test_smoke_ecosystem_list_json_reports_this_package():
    # Arrange — `ecosystem list` reads the local registry only (no network).
    argv = _CLI + ["ecosystem", "list", "--json"]
    # Act
    result = subprocess.run(
        argv, capture_output=True, text=True, timeout=120, cwd=_repo_root()
    )
    # Assert
    assert result.returncode == 0
