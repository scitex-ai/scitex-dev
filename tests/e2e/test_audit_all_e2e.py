#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end layer — slow workflows against real subsystems, loopback only.

Gated by ``RUN_E2E=1`` and skipped by default (``pytest -m e2e`` selects
the layer; the gate decides whether it RUNS). Each test drives the real
CLI in a subprocess against this checkout — no network, no mocks, no
``monkeypatch``; isolation comes from the session shield in
``tests/conftest.py``, inherited by the child.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("RUN_E2E") != "1",
        reason="e2e: set RUN_E2E=1 to run end-to-end workflows",
    ),
]

_CLI = [sys.executable, "-m", "scitex_dev"]


def _repo_root() -> str:
    """Checkout root — the tree this test file lives in."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_e2e_audit_project_reports_zero_errors_on_self():
    # Arrange — the auditor audits its own checkout (loopback only).
    argv = _CLI + [
        "ecosystem",
        "audit-project",
        "scitex-dev",
        "--path",
        _repo_root(),
        "--severity",
        "warning",
        "--json",
    ]
    # Act
    result = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    # Assert — exactly one observable: the machine-readable error count.
    assert json.loads(result.stdout)["errors"] == 0
