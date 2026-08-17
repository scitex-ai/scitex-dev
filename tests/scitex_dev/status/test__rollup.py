#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :func:`scitex_dev.status.rollup`.

The load-bearing property is that the SAME set of checks rolls up to different
verdicts under different policies, and that the caller has to choose. If a
default ever creeps in, the tests that pin REFUSE and TOLERATE against one
shared fixture stop meaning anything — so they are written against one shared
fixture deliberately.

The second property is that an unknown is never silent. Under every policy the
summary names it, because an aggregate answering "ok" without saying what it
could not see has lied by omission.

Refusals are captured by :func:`_rollup_refusal` and returned rather than
asserted inside a ``raises`` block, keeping each test to ONE assertion.
"""

from __future__ import annotations

from scitex_dev.status import Check, UnknownPolicy, Verdict, rollup

_WHY = "the host refused the probe with http 403; its daemon predates the endpoint"
_HOW = "upgrade the remote daemon, then re-run `sac relocate --check`"


def _mixed():
    """One passing check and one that could not find out. No failures."""
    return [
        Check.ok("store_canonical", "PostgreSQL store, 3469 cards, writable"),
        Check.unknown("may_relocate", _WHY, _HOW),
    ]


def _rollup_refusal(checks, **kwargs):
    """Roll up and return the refusal it raised, or None."""
    try:
        rollup("scitex-cards", checks, **kwargs)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- the same checks, three answers, because the caller chooses ---------------


def test_refuse_turns_an_unknown_into_a_blocking_not_ok():
    """Never move an agent onto a host you could not inspect."""
    # Arrange
    checks = _mixed()
    # Act
    report = rollup("relocation", checks, unknown_policy=UnknownPolicy.REFUSE)
    # Assert
    assert report.verdict is Verdict.NOT_OK


def test_propagate_reports_the_rollup_itself_as_unknown():
    """"I cannot tell you the whole is healthy" is what actually happened."""
    # Arrange
    checks = _mixed()
    # Act
    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.PROPAGATE)
    # Assert
    assert report.verdict is Verdict.UNKNOWN


def test_tolerate_lets_the_rollup_answer_ok():
    """The question there is "may I proceed?", not "is everything known?"."""
    # Arrange
    checks = _mixed()
    # Act
    report = rollup("dashboard", checks, unknown_policy=UnknownPolicy.TOLERATE)
    # Assert
    assert report.verdict is Verdict.OK


# -- a known failure always wins ----------------------------------------------


def test_a_known_failure_outranks_an_unknown_under_tolerate():
    """A definite problem is not made less definite by an unknown beside it."""
    # Arrange
    checks = _mixed() + [Check.not_ok("notifyd_alive", "no pidfile", "start notifyd")]
    # Act
    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.TOLERATE)
    # Assert
    assert report.verdict is Verdict.NOT_OK


def test_a_known_failure_outranks_an_unknown_under_propagate():
    """Same precedence under the policy that would otherwise answer unknown."""
    # Arrange
    checks = _mixed() + [Check.not_ok("notifyd_alive", "no pidfile", "start notifyd")]
    # Act
    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.PROPAGATE)
    # Assert
    assert report.verdict is Verdict.NOT_OK


def test_a_queued_check_does_not_count_as_a_pass():
    """The auto-merge sweep's exact failure, made executable.

    Its greenness filter dropped QUEUED checks, so "not yet known" was counted
    as "passing" and it merged unverified code past branch protection with
    `--admin` — in two repositories independently. A queued check is `unknown`,
    and under REFUSE it blocks.
    """
    # Arrange
    checks = [
        Check.ok("lint", "passed in 41s"),
        Check.unknown(
            "pytest-matrix",
            "queued; the run has no conclusion yet, so nothing has been verified",
            "re-read `gh pr checks` once the run settles",
        ),
    ]
    # Act
    report = rollup("automerge", checks, unknown_policy=UnknownPolicy.REFUSE)
    # Assert
    assert report.verdict is Verdict.NOT_OK


def test_all_passing_checks_roll_up_to_ok_under_refuse():
    """REFUSE blocks on unknowns, not on everything — the strict policy still passes."""
    # Arrange
    checks = [Check.ok("store_canonical", "writable"), Check.ok("agent_id", "resolved")]
    # Act
    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.REFUSE)
    # Assert
    assert report.verdict is Verdict.OK


# -- the policy is required, and nothing supplies it for you ------------------


def test_rollup_refuses_a_missing_unknown_policy():
    """A default policy is the boolean collapse moved one level up and hidden."""
    # Arrange
    checks = _mixed()
    # Act
    refusal = _rollup_refusal(checks)
    # Assert
    assert isinstance(refusal, TypeError)


def test_rollup_refuses_a_bare_string_policy():
    """The policy is a decision, so it is spelled as one of the three members."""
    # Arrange
    checks = _mixed()
    # Act
    refusal = _rollup_refusal(checks, unknown_policy="tolerate")
    # Assert
    assert refusal is not None


def test_rollup_refuses_an_unvalidated_dict_in_place_of_a_check():
    """A bare dict skipped the rules that make an unknown worth more than a boolean."""
    # Arrange
    checks = [{"name": "store_canonical", "ok": True, "detail": "writable"}]
    # Act
    refusal = _rollup_refusal(checks, unknown_policy=UnknownPolicy.TOLERATE)
    # Assert
    assert refusal is not None


# -- an unknown is never silent -----------------------------------------------


def test_a_tolerated_unknown_is_still_named_in_the_summary():
    """Tolerating an unknown is not hiding it — this is the never-silent rule."""
    # Arrange
    report = rollup("dashboard", _mixed(), unknown_policy=UnknownPolicy.TOLERATE)
    # Act
    summary = report.summary
    # Assert
    assert "unknown: may_relocate" in summary


def test_the_summary_counts_only_the_checks_that_actually_passed():
    """An unknown must not be counted as a pass, which is the arithmetic form of the bug."""
    # Arrange
    report = rollup("dashboard", _mixed(), unknown_policy=UnknownPolicy.TOLERATE)
    # Act
    summary = report.summary
    # Assert
    assert summary.startswith("1/2 checks passed")


def test_the_report_lists_the_unknown_checks_by_name():
    """A caller deciding what to do next needs the names, not just the count."""
    # Arrange
    report = rollup("dashboard", _mixed(), unknown_policy=UnknownPolicy.TOLERATE)
    # Act
    names = report.unknown
    # Assert
    assert names == ("may_relocate",)


# -- an empty set has established nothing -------------------------------------


def test_an_empty_check_set_blocks_under_refuse():
    """A doctor that ran nothing has not established that anything is fine."""
    # Arrange
    checks = []
    # Act
    report = rollup("relocation", checks, unknown_policy=UnknownPolicy.REFUSE)
    # Assert
    assert report.verdict is Verdict.NOT_OK


def test_an_empty_check_set_is_unknown_under_propagate():
    """Nothing was measured, so nothing can be reported about the whole."""
    # Arrange
    checks = []
    # Act
    report = rollup("scitex-cards", checks, unknown_policy=UnknownPolicy.PROPAGATE)
    # Assert
    assert report.verdict is Verdict.UNKNOWN


# -- the wire form ------------------------------------------------------------


def test_the_report_serialises_to_exactly_the_four_familiar_keys():
    """The doctors that already publish this shape keep every reader they have."""
    # Arrange
    report = rollup("scitex-cards", _mixed(), unknown_policy=UnknownPolicy.TOLERATE)
    # Act
    keys = set(report.to_dict())
    # Assert
    assert keys == {"package", "ok", "checks", "summary"}


def test_a_tolerating_rollup_publishes_a_real_boolean_ok():
    """TOLERATE never answers unknown, so its top-level `ok` stays a plain bool."""
    # Arrange
    report = rollup("scitex-cards", _mixed(), unknown_policy=UnknownPolicy.TOLERATE)
    # Act
    published = report.to_dict()["ok"]
    # Assert
    assert published is True


def test_a_propagating_rollup_publishes_json_null_for_unknown():
    """The third state reaches the wire intact, in the same field as the other two."""
    # Arrange
    report = rollup("scitex-cards", _mixed(), unknown_policy=UnknownPolicy.PROPAGATE)
    # Act
    published = report.to_dict()["ok"]
    # Assert
    assert published is None


# EOF
