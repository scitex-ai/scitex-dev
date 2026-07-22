# -*- coding: utf-8 -*-
"""Unit tests for `parse_enforce_logging` — PS-220's per-package opt-in.

PS-220 is a STAGED rollout: warning by default, and each package opts IN to
error once its print migration lands. The opt-in must SAY WHY, so `error`
and `off` demand a written reason and a bare shorthand is rejected. These
tests exercise the parser directly (no config file, no auditor) so each
accept/reject decision is pinned in isolation; `test__check_no_print.py`
covers the same surface end-to-end through `load_config`.
"""

from __future__ import annotations

from scitex_dev._cli.audit._config._enforce_logging import (
    ENFORCE_LOGGING_REASONED_LEVELS,
    ENFORCE_LOGGING_VALUES,
    parse_enforce_logging,
)


# --- nothing declared --------------------------------------------------------


def test_absent_block_yields_no_level_and_no_rejection():
    # Arrange
    raw = None
    # Act
    level, reason, errors = parse_enforce_logging(raw)
    # Assert
    assert (level, reason, errors) == (None, None, ())


# --- the mapping form (canonical) --------------------------------------------


def test_mapping_error_with_a_reason_is_accepted_as_error():
    # Arrange
    raw = {"level": "error", "reason": "migration complete (PR #412)"}
    # Act
    level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert (level, errors) == ("error", ())


def test_mapping_error_with_a_reason_returns_that_reason_stripped():
    # Arrange
    raw = {"level": "error", "reason": "  migration complete  "}
    # Act
    _level, reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert reason == "migration complete"


def test_mapping_off_with_a_reason_is_accepted_as_off():
    # Arrange
    raw = {"level": "off", "reason": "vendored third-party tree"}
    # Act
    level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert (level, errors) == ("off", ())


def test_mapping_warning_without_a_reason_is_accepted():
    # Arrange — warning is the default, so it changes nothing
    raw = {"level": "warning"}
    # Act
    level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert (level, errors) == ("warning", ())


def test_yaml_boolean_false_level_is_read_as_off():
    # Arrange — YAML 1.1 parses bare `off`/`no` as boolean False
    raw = {"level": False, "reason": "vendored third-party tree"}
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level == "off"


def test_yaml_boolean_true_level_is_read_as_error():
    # Arrange — YAML 1.1 parses bare `on`/`yes` as boolean True
    raw = {"level": True, "reason": "migration complete"}
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level == "error"


# --- the mandatory reason ----------------------------------------------------


def test_mapping_error_without_a_reason_does_not_take_effect():
    # Arrange
    raw = {"level": "error"}
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_mapping_error_without_a_reason_is_reported_as_rejected():
    # Arrange
    raw = {"level": "error"}
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert len(errors) == 1 and "REJECTED" in errors[0]


def test_mapping_error_with_a_whitespace_only_reason_does_not_take_effect():
    # Arrange — a reason made of spaces is not a stated reason
    raw = {"level": "error", "reason": "   \t  "}
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_mapping_off_without_a_reason_does_not_take_effect():
    # Arrange — the strongest suppression must never be reasonless
    raw = {"level": "off"}
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_mapping_without_a_level_is_reported_as_missing_level():
    # Arrange
    raw = {"reason": "we tried"}
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert len(errors) == 1 and "missing `level`" in errors[0]


def test_mapping_with_an_unknown_level_is_reported_as_unrecognised():
    # Arrange
    raw = {"level": "maybe", "reason": "typo"}
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert len(errors) == 1 and "not a recognised level" in errors[0]


# --- the bare-scalar shorthand -----------------------------------------------


def test_bare_warning_scalar_is_accepted():
    # Arrange
    raw = "warning"
    # Act
    level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert (level, errors) == ("warning", ())


def test_bare_error_scalar_does_not_take_effect():
    # Arrange — the pre-staging spelling carries no reason
    raw = "error"
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_bare_error_scalar_is_reported_as_rejected():
    # Arrange
    raw = "error"
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert len(errors) == 1 and "REJECTED" in errors[0]


def test_bare_error_rejection_names_the_mapping_form_as_the_remedy():
    # Arrange — a rejection that does not say what to write instead is a wall
    raw = "error"
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert "reason" in errors[0] and "level" in errors[0]


def test_bare_off_scalar_does_not_take_effect():
    # Arrange
    raw = "off"
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_bare_yaml_boolean_false_does_not_take_effect():
    # Arrange — `enforce-logging: off` reaches us as boolean False
    raw = False
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_bare_yaml_boolean_true_does_not_take_effect():
    # Arrange — `enforce-logging: on` reaches us as boolean True
    raw = True
    # Act
    level, _reason, _errors = parse_enforce_logging(raw)
    # Assert
    assert level is None


def test_bare_unknown_scalar_is_reported_as_unrecognised():
    # Arrange — a typo must fall back LOUDLY, not silently
    raw = "maybe"
    # Act
    _level, _reason, errors = parse_enforce_logging(raw)
    # Assert
    assert len(errors) == 1 and "not a recognised level" in errors[0]


# --- the constants themselves ------------------------------------------------


def test_warning_is_the_only_level_exempt_from_the_reason_requirement():
    # Arrange
    # Act
    reasonless_ok = ENFORCE_LOGGING_VALUES - ENFORCE_LOGGING_REASONED_LEVELS
    # Assert
    assert reasonless_ok == {"warning"}


# EOF
