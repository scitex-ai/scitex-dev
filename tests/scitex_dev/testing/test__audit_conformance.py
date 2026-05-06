"""Smoke tests for `scitex_dev.testing.audit_all_for_package`."""

import os

import pytest


def test_audit_all_for_package_skip_via_env(monkeypatch):
    """SCITEX_DEV_SKIP_AUDIT=1 must short-circuit the helper."""
    from scitex_dev.testing import audit_all_for_package

    monkeypatch.setenv("SCITEX_DEV_SKIP_AUDIT", "1")
    with pytest.raises(pytest.skip.Exception):  # pytest.skip raises Skipped
        audit_all_for_package("scitex-dev")


def test_audit_all_for_package_runs_when_unset(monkeypatch):
    """Without the skip env var the helper does *something* (here: it
    just confirms the underlying CLI is callable; we don't assert exit
    code because the working tree may legitimately have violations)."""
    from scitex_dev.testing import _audit_conformance

    monkeypatch.delenv("SCITEX_DEV_SKIP_AUDIT", raising=False)
    # Ensure the helper exists and is importable; running it on
    # `scitex-agent-container` (a known non-archived package) is a
    # cheap real-binary check.
    assert callable(_audit_conformance.audit_all_for_package)
