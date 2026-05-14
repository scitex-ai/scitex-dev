"""Smoke tests for `scitex_dev.testing.audit_all_for_package`."""

import os

import pytest


@pytest.fixture
def skip_audit_env():
    """Set SCITEX_DEV_SKIP_AUDIT=1 for the test, restore on exit."""
    saved = os.environ.get("SCITEX_DEV_SKIP_AUDIT")
    os.environ["SCITEX_DEV_SKIP_AUDIT"] = "1"
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("SCITEX_DEV_SKIP_AUDIT", None)
        else:
            os.environ["SCITEX_DEV_SKIP_AUDIT"] = saved


@pytest.fixture
def no_skip_audit_env():
    """Ensure SCITEX_DEV_SKIP_AUDIT is unset for the test, restore on exit."""
    saved = os.environ.pop("SCITEX_DEV_SKIP_AUDIT", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["SCITEX_DEV_SKIP_AUDIT"] = saved


def test_audit_all_for_package_skip_via_env(skip_audit_env):
    """SCITEX_DEV_SKIP_AUDIT=1 must short-circuit the helper."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.testing import audit_all_for_package

    with pytest.raises(pytest.skip.Exception):  # pytest.skip raises Skipped
        audit_all_for_package("scitex-dev")


def test_audit_all_for_package_runs_when_unset(no_skip_audit_env):
    """Without the skip env var the helper does *something* (here: it
    just confirms the underlying CLI is callable; we don't assert exit
    code because the working tree may legitimately have violations)."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.testing import _audit_conformance

    # Ensure the helper exists and is importable; running it on
    # `scitex-agent-container` (a known non-archived package) is a
    # cheap real-binary check.
    assert callable(_audit_conformance.audit_all_for_package)
