# -*- coding: utf-8 -*-
"""audit-cli must not relabel warnings as errors.

`_emit_human` computed ONE severity for the whole run
(`sev = _max_severity(violations)`) and then printed every violation —
and the count noun — at that single level. Measured on CI (PR #447,
py3.13 leg, sha 1696b80), one genuine §10 import-budget breach
relabelled six standing §12/§13 warn-tier findings as `ERRO:` and
reported::

    ERRO: scitex-dev: CLI conventions: 7 error(s)
    ERRO:   [§10] ...
    ERRO:   [§12] ...
    ERRO:   [§13] ...   (x5)

There was exactly ONE error and six warnings. A narrow timing breach
therefore read as a broad structural break, which cost real diagnosis
time, and the wrong count propagated: `_audit_masking.is_error_line`
reads severity off that very `ERRO:` prefix, so audit-all's
"N unmasked error(s)" tally inherited the lie from a renderer bug —
defeating a downstream counter whose own docstring already insisted
"a run with 7 warnings and 1 error is not 8 errors".

WHY caplog AND NOT capfd. Same reasoning as
`_project/test__audit_summary_counts.py`, measured there rather than
assumed: `_emit` logs through `scitex_logging.getLogger`
("scitex_dev.audit"), which carries no handlers of its own and reaches a
terminal only by propagating to ambient root handlers. Reading the
logging transport is deterministic AND strictly stronger — it pins the
LEVEL of every line, which is the entire subject of these tests.

No mocks (STX-NM002): the real `_emit_human` renders real `Violation`
objects whose rules are real entries in the real `RULE_SEVERITY`
registry. Nothing is patched.
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("click")

# Imported for its SIDE EFFECT as much as its name — see the long note in
# `_project/test__audit_summary_counts.py`: `_emit` can only bind a
# `SciTeXLogger` if nothing created the `scitex_dev.audit` name through the
# stdlib first. Importing here closes that window for this module, and the
# tests below never pass `logger=` to `caplog.set_level`.
from scitex_dev._cli.audit import _emit as _emit_module  # noqa: F401,E402
from scitex_dev._cli.audit._summary._audit import Violation  # noqa: E402
from scitex_dev._cli.audit._summary._run import _emit_human  # noqa: E402


_PKG = "scitex-dev"

# The exact finding set off the failing CI leg: one §10 (error tier) and
# six §12/§13 (warn tier), all of which existed on develop unchanged.
_ONE_ERROR_SIX_WARNINGS = [
    Violation(_PKG, "§10", "`import scitex_dev` adds 614ms over bare-interpreter"),
    Violation(_PKG, "§12", "`gui` group is missing required verb(s) serve, status"),
    Violation(_PKG, "§13", "ecosystem cron must nest under a `dev` group"),
    Violation(_PKG, "§13", "ecosystem systemd must nest under a `dev` group"),
    Violation(_PKG, "§13", "skills must nest under a `dev` group"),
    Violation(_PKG, "§13", "cron must nest under a `dev` group"),
    Violation(_PKG, "§13", "hooks must nest under a `dev` group"),
]

# Positive control: an all-error set. Guards against "fixing" the
# collapse by simply downgrading everything to warning.
_ALL_ERRORS = [
    Violation(_PKG, "§10", "import budget blown"),
    Violation(_PKG, "§2", "interactive prompt in source"),
    Violation(_PKG, "§11", "env var outside the allowlist"),
]


def _render(caplog, violations):
    """Run the REAL renderer and return [(levelno, message), ...].

    Numeric level, not `levelname`: scitex-logging re-registers the
    level NAMES globally (`WARNING` renders as `WARN`, `ERROR` as
    `ERRO`), so a name comparison would assert on presentation and pass
    or fail depending on whether scitex-logging happened to be imported.
    `levelno` is the severity itself.
    """
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _emit_human(_PKG, "warn", violations, category="CLI convention")
    return [(r.levelno, r.getMessage()) for r in caplog.records]


def _headline(lines):
    """The `<pkg>: CLI conventions: ...` summary line, as (levelno, msg)."""
    return next(lvl_msg for lvl_msg in lines if "CLI conventions:" in lvl_msg[1])


def _finding_levels(lines, rule):
    """Numeric levels at which the findings for `rule` were emitted."""
    return [lvl for lvl, msg in lines if f"[{rule}]" in msg]


# --------------------------------------------------------------------- #
# THE REGRESSION — 1 error + 6 warnings.                                 #
# On develop these fail: the headline reads "7 error(s)" and every       #
# finding line, §12 and §13 included, is emitted at ERROR.               #
# --------------------------------------------------------------------- #


class TestMixedSeveritiesRenderIndependently:
    def test_headline_reports_the_error_count(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert
        assert "1 error(s)" in message

    def test_headline_reports_the_warning_count(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert
        assert "6 warning(s)" in message

    def test_headline_no_longer_calls_seven_findings_errors(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert — the exact string CI printed.
        assert "7 error(s)" not in message

    def test_headline_stays_at_error_level(self, caplog):
        # Arrange — a run containing a real error must still LOOK red.
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        level, _message = _headline(_render(caplog, violations))
        # Assert
        assert level == logging.ERROR

    def test_error_tier_finding_is_emitted_at_error(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        levels = _finding_levels(_render(caplog, violations), "§10")
        # Assert
        assert levels == [logging.ERROR]

    def test_gui_warning_is_not_emitted_at_error(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        levels = _finding_levels(_render(caplog, violations), "§12")
        # Assert
        assert levels == [logging.WARNING]

    def test_all_five_dev_group_warnings_are_emitted_at_warning(self, caplog):
        # Arrange
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        levels = _finding_levels(_render(caplog, violations), "§13")
        # Assert
        assert levels == [logging.WARNING] * 5

    def test_every_finding_is_still_printed(self, caplog):
        # Arrange — per-severity rendering must not drop any finding.
        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        lines = _render(caplog, violations)
        # Assert
        assert sum(1 for _lvl, msg in lines if msg.lstrip().startswith("[")) == 7


# --------------------------------------------------------------------- #
# POSITIVE CONTROL — the fix must not be "downgrade everything".         #
# --------------------------------------------------------------------- #


class TestAllErrorSetStillReportsErrors:
    def test_headline_counts_every_error(self, caplog):
        # Arrange
        violations = _ALL_ERRORS
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert
        assert "3 error(s)" in message

    def test_headline_reports_zero_warnings_explicitly(self, caplog):
        # Arrange — the zero band is printed, so "no warnings" and
        # "warnings not counted" stay distinguishable.
        violations = _ALL_ERRORS
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert
        assert "0 warning(s)" in message

    def test_every_finding_is_emitted_at_error(self, caplog):
        # Arrange
        violations = _ALL_ERRORS
        # Act
        lines = _render(caplog, violations)
        levels = [lvl for lvl, msg in lines if msg.lstrip().startswith("[")]
        # Assert
        assert levels == [logging.ERROR] * 3

    def test_warn_only_run_reports_zero_errors(self, caplog):
        # Arrange — the other direction: no error may be invented.
        violations = [v for v in _ONE_ERROR_SIX_WARNINGS if v.rule != "§10"]
        # Act
        _level, message = _headline(_render(caplog, violations))
        # Assert
        assert "0 error(s), 6 warning(s)" in message

    def test_warn_only_headline_is_not_error_level(self, caplog):
        # Arrange
        violations = [v for v in _ONE_ERROR_SIX_WARNINGS if v.rule != "§10"]
        # Act
        level, _message = _headline(_render(caplog, violations))
        # Assert
        assert level == logging.WARNING


# --------------------------------------------------------------------- #
# The machine path carries severity as its own named field.              #
# --------------------------------------------------------------------- #


class TestJsonRecordCarriesSeverity:
    def test_error_tier_violation_reports_error(self):
        # Arrange
        from scitex_dev._cli.audit._summary._run import _violation_to_dict

        violation = _ONE_ERROR_SIX_WARNINGS[0]
        # Act
        record = _violation_to_dict(violation)
        # Assert
        assert record["severity"] == "error"

    def test_warn_tier_violation_reports_warn(self):
        # Arrange
        from scitex_dev._cli.audit._summary._run import _violation_to_dict

        violation = _ONE_ERROR_SIX_WARNINGS[1]
        # Act
        record = _violation_to_dict(violation)
        # Assert
        assert record["severity"] == "warn"

    def test_severity_counts_are_per_band(self):
        # Arrange
        from scitex_dev._cli.audit._summary._severity import severity_counts

        violations = _ONE_ERROR_SIX_WARNINGS
        # Act
        counts = severity_counts(violations)
        # Assert
        assert counts == {"error": 1, "warn": 6, "info": 0}
