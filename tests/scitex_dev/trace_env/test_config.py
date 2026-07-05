"""Tests for ``scitex_dev.trace_env.config`` — matching + redaction helpers.

Pins the pure helpers ``config.py`` exports (the dataclasses plus the
matching/redaction primitives the scan/trace layers build on):

* WORD-BOUNDARY matching — searching ``FOO`` must NOT match ``FOO_BAR``
  (the operator's real pitfall: ``SCITEX_TODO_AGENT`` vs
  ``SCITEX_TODO_AGENT_ID``).
* Secret-shaped detection + redaction — secret-shaped values are replaced
  with ``<redacted: N chars>`` in ALL output.

Scan-integration (``scan_env_vars``) and trace-integration
(``trace_env_vars`` + strace parsing) live in ``test_scan.py`` /
``test_trace.py`` alongside their own src modules.
"""

from __future__ import annotations

import pytest

from scitex_dev.trace_env import assignment_regex, is_secret_shaped, redact


# --------------------------------------------------------------------
# WORD-BOUNDARY correctness — the key pitfall of this tool.
# --------------------------------------------------------------------


def test_assignment_regex_matches_bare_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO=1")
    # Assert
    assert hit


def test_assignment_regex_matches_export_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("export FOO=1")
    # Assert
    assert hit


def test_assignment_regex_matches_spaced_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO = 1")
    # Assert
    assert hit


def test_assignment_regex_rejects_longer_suffix_identifier():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO_BAR=1")
    # Assert
    assert not hit


def test_assignment_regex_rejects_longer_prefix_identifier():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("PREFIX_FOO=1")
    # Assert
    assert not hit


def test_assignment_regex_rejects_equality_comparison():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO==1")
    # Assert
    assert not hit


# --------------------------------------------------------------------
# Redaction — secret-shaped values never printed.
# --------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["API_KEY", "GH_TOKEN", "DB_PASSWORD", "MY_PASS", "X_SECRET",
     "AWS_CREDENTIAL", "SOME_AUTH", "A_COOKIE", "SCITEX_TODO_SESSION"],
)
def test_is_secret_shaped_true(name):
    # Arrange
    # Act
    shaped = is_secret_shaped(name)
    # Assert
    assert shaped


@pytest.mark.parametrize("name", ["SCITEX_TODO_AGENT", "PATH", "HOME", "KEYBOARD"])
def test_is_secret_shaped_false(name):
    # Arrange
    # Act
    shaped = is_secret_shaped(name)
    # Assert
    assert not shaped


def test_redact_replaces_secret_value():
    # Arrange
    # Act
    out = redact("API_KEY", "supersecret")
    # Assert
    assert out == "<redacted: 11 chars>"


def test_redact_passes_through_nonsecret_value():
    # Arrange
    # Act
    out = redact("PATH", "/usr/bin")
    # Assert
    assert out == "/usr/bin"


def test_redact_passes_through_none():
    # Arrange
    # Act
    out = redact("API_KEY", None)
    # Assert
    assert out is None
