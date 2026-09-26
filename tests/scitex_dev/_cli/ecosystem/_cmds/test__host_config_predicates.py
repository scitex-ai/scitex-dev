#!/usr/bin/env python3
"""The two predicates that decide whether `host-config check` exits non-zero.

MEASURED 2026-09-02 on scitex-compute-04, which is why these exist:

    blocked        auditd.process-kill   'auditctl' is not installed
    would-create   dhcp.requested-address.scitex-compute-04
    would-create   journald.persistent
    3 spec(s) not in the declared state       exit 1

`blocked` was counted as drift. auditctl may never be installed on that
host, so the command would exit non-zero forever and the unit could never
go green. A gate that cannot PASS is as useless as one that cannot fail,
and it costs the alarm for the two rows that ARE actionable.

The scheduled job wraps the command in `|| true`, which discards the
verdict entirely -- probably for exactly this reason. Making `blocked`
not-drift is what lets that wrapper be removed.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.ecosystem._cmds._host_config import (
    is_actionable_drift,
    is_blocked,
)


class TestBlockedIsReportedButNotDrift:
    """A host that CANNOT honour a declaration has not drifted from it."""

    def test_blocked_is_recognised_as_blocked(self):
        # Arrange
        action = "blocked"

        # Act
        result = is_blocked(action)

        # Assert
        assert result is True

    def test_blocked_is_not_actionable_drift(self):
        # Arrange
        action = "blocked"

        # Act
        result = is_actionable_drift(action)

        # Assert — this is the whole fix. Counting it would make the exit
        # code non-zero forever on a host missing the tool.
        assert result is False


class TestStatesThatSomeoneCanAct_On:
    """Rows a person can bring into the declared state SHOULD exit non-zero."""

    @pytest.mark.parametrize(
        "action", ["drift", "reload-failed", "would-create", "would-update"]
    )
    def test_actionable_states_count_as_drift(self, action):
        # Arrange
        subject = action

        # Act
        result = is_actionable_drift(subject)

        # Assert
        assert result is True

    @pytest.mark.parametrize("action", ["unchanged", "skipped"])
    def test_settled_states_do_not_count_as_drift(self, action):
        # Arrange
        subject = action

        # Act
        result = is_actionable_drift(subject)

        # Assert
        assert result is False


class TestAnUnknownActionIsTreatedAsDrift:
    """Fail toward the alarm, not away from it."""

    def test_an_unrecognised_action_counts_as_drift(self):
        # Arrange — a new action added later, not yet taught to this module.
        action = "some-future-action"

        # Act
        result = is_actionable_drift(action)

        # Assert — an unknown state must not silently become "fine". The
        # only states that mean "nothing to do" are named explicitly.
        assert result is True

    def test_an_unrecognised_action_is_not_treated_as_blocked(self):
        # Arrange
        action = "some-future-action"

        # Act
        result = is_blocked(action)

        # Assert — `blocked` suppresses the exit code, so it must be an
        # exact membership test. Guessing a row is blocked would silence
        # a real deviation.
        assert result is False
