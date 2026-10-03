"""Owned state + genuine lock tests; all transport is an in-memory API fake."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from scitex_dev.ci.runner import _policy_observer
from scitex_dev.ci.runner._policy_observer import (
    ASSIGNEE,
    STORE_INSTANCE,
    STORE_UUID,
    TASK_ID,
    observe_once,
)


def test_absent_optional_cards_refuses_durable_alert_in_fresh_process(tmp_path):
    """Bare Dev may omit Cards; cron must expose that delivery is unavailable."""
    # Arrange
    source_root = Path(__file__).resolve().parents[4] / "src"
    child = r"""
from pathlib import Path
import importlib.abc
import json
import sys
sys.path.insert(0, sys.argv[1])
class AbsentCards(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "scitex_cards" or fullname.startswith("scitex_cards."):
            raise ModuleNotFoundError("synthetic absent optional Cards", name=fullname)
sys.meta_path.insert(0, AbsentCards())
from scitex_dev.ci.runner._policy_observer import observe_once
result = observe_once(
    state_dir=Path(sys.argv[2]),
    collector=lambda: {"state":"violation", "violations":["fixture"], "unknown":[]},
)
print(json.dumps(result))
"""
    state = tmp_path / "state"
    # Act
    result = subprocess.run(
        [sys.executable, "-I", "-c", child, str(source_root), str(state)],
        env={"HOME": str(tmp_path), "PATH": os.defpath},
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    observation = json.loads(result.stdout)
    # Assert
    assert {
        **{
            key: observation[key]
            for key in ("exit_code", "delivery", "exception_type", "refusal_reason")
        },
        "delivery_intent_persisted": (state / "state.json").exists(),
    } == {
        "exit_code": 1,
        "delivery": "refused-or-unknown",
        "exception_type": "PolicyObserverError",
        "refusal_reason": "Cards package unavailable; no durable policy alert",
        "delivery_intent_persisted": False,
    }


class _MissingCard(Exception):
    pass


class _Cards:
    TaskNotFoundError = _MissingCard

    def __init__(self):
        self.target = {
            "may_proceed": True,
            "store_uuid": STORE_UUID,
            "expected_uuid": STORE_UUID,
            "instance_id": STORE_INSTANCE,
            "expected_instance": STORE_INSTANCE,
        }
        self.card = {
            "id": TASK_ID,
            "assignee": ASSIGNEE,
            "agent": ASSIGNEE,
            "status": "in_progress",
            "comments": [],
        }
        self.writes = []
        self.reads = 0
        self.failure = None

    def resolve_store(self):
        self.reads += 1
        return dict(self.target)

    def get_task(self, *, task_id):
        if self.card is None:
            raise _MissingCard()
        return deepcopy(self.card)

    def add_task(self, **fields):
        self.writes.append(("create", fields))
        self.card = dict(fields, agent=fields["assignee"], comments=[])
        return deepcopy(self.card)

    def comment_task(self, *, task_id, text, by, kind):
        if self.failure == "before-write":
            raise ConnectionError("fixture failure; not a production credential")
        entry = {
            "id": "c_" + str(len(self.card["comments"])),
            "text": text,
            "author": by,
        }
        self.card["comments"].append(entry)
        self.writes.append(("comment", entry))
        if self.failure == "after-commit":
            raise ConnectionError("fixture unknown outcome")
        return deepcopy(entry)


def _report(state="violation", busy=None):
    return {
        "state": state,
        "violations": ["unrestricted workflow access"] if state == "violation" else [],
        "unknown": ["workflow inventory unavailable"] if state == "unknown" else [],
        "groups": [],
        "workflow_source": {},
        "organization": "scitex-ai",
        "observed_at": "2026-10-03T06:00:00+00:00",
        "activity": {
            "busy_runners": busy or [],
            "last_completed_job_at": None,
            "last_completed_job_age_s": None,
            "sample_complete": False,
        },
    }


def _pass(root, api, *, state="violation", now=0, busy=None, dry_run=False):
    return observe_once(
        state_dir=root,
        cards_api=api,
        collector=lambda: _report(state, busy),
        clock=lambda: now,
        dry_run=dry_run,
    )


def test_first_violation_has_exact_official_card_readback(tmp_path):
    # Arrange
    api = _Cards()
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (
        result["delivery"],
        result["exit_code"],
        result["comment_id"],
        len(api.writes),
    ) == ("alert-confirmed", 1, "c_0", 1)


def test_busy_change_is_not_new_policy_or_productive_progress(tmp_path):
    # Arrange
    api = _Cards()
    _pass(tmp_path, api)
    # Act
    result = _pass(tmp_path, api, now=900, busy=["scitex-ci-03"])
    # Assert
    assert (
        result["delivery"],
        len(api.writes),
        result["report"]["activity"]["last_completed_job_age_s"],
    ) == ("deduplicated", 1, None)


def test_reordered_workflow_acl_is_the_same_condition(tmp_path):
    # Arrange
    api = _Cards()
    first = _report()
    first["groups"] = [{"id": 6, "selected_workflows": ["ref-one", "ref-two"]}]
    observe_once(
        state_dir=tmp_path, cards_api=api, collector=lambda: first, clock=lambda: 0
    )
    second = _report()
    second["groups"] = [{"selected_workflows": ["ref-two", "ref-one"], "id": 6}]
    # Act
    result = observe_once(
        state_dir=tmp_path, cards_api=api, collector=lambda: second, clock=lambda: 900
    )
    # Assert
    assert (result["delivery"], len(api.writes)) == ("deduplicated", 1)


def test_unchanged_condition_reminder_is_hourly(tmp_path):
    # Arrange
    api = _Cards()
    _pass(tmp_path, api)
    # Act
    earlier = _pass(tmp_path, api, now=3599)
    due = _pass(tmp_path, api, now=3600)
    # Assert
    assert (earlier["delivery"], due["delivery"], len(api.writes)) == (
        "deduplicated",
        "reminder-confirmed",
        2,
    )


def test_recovery_is_delivered_once(tmp_path):
    # Arrange
    api = _Cards()
    _pass(tmp_path, api)
    # Act
    recovered = _pass(tmp_path, api, state="conformant", now=900)
    later = _pass(tmp_path, api, state="conformant", now=1800)
    # Assert
    assert (
        recovered["delivery"],
        recovered["exit_code"],
        later["delivery"],
        len(api.writes),
    ) == ("recovery-confirmed", 0, "no-alert-needed", 2)


def test_unknown_policy_alert_does_not_claim_runner_stopped(tmp_path):
    # Arrange
    api = _Cards()
    # Act
    result = _pass(tmp_path, api, state="unknown")
    # Assert
    assert (
        result["delivery"],
        "Last completed job (bounded Dev sample): unknown" in api.writes[0][1]["text"],
        "stopped" in api.writes[0][1]["text"],
    ) == ("alert-confirmed", True, False)


@pytest.mark.parametrize(
    "field,value",
    [
        ("may_proceed", False),
        ("store_uuid", "foreign"),
        ("expected_uuid", None),
        ("instance_id", "different"),
        ("expected_instance", None),
    ],
)
def test_uuid_instance_or_admission_uncertainty_refuses_all_writes(
    tmp_path, field, value
):
    # Arrange
    api = _Cards()
    api.target[field] = value
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (
        result["delivery"],
        result["exit_code"],
        api.writes,
        (tmp_path / "state.json").exists(),
    ) == ("refused-or-unknown", 1, [], False)


def test_failed_write_stays_pending_without_blind_tick_retry(tmp_path):
    # Arrange
    api = _Cards()
    api.failure = "before-write"
    # Act
    first = _pass(tmp_path, api)
    later = _pass(tmp_path, api, now=900)
    saved = json.loads((tmp_path / "state.json").read_text())
    # Assert
    assert (
        first["delivery"],
        later["delivery"],
        later["exit_code"],
        api.writes,
        "pending" in saved,
    ) == ("refused-or-unknown", "unknown-pending", 1, [], True)


def test_unknown_committed_write_is_reconciled_without_duplicate(tmp_path):
    # Arrange
    api = _Cards()
    api.failure = "after-commit"
    _pass(tmp_path, api)
    api.failure = None
    # Act
    result = _pass(tmp_path, api, now=900)
    # Assert
    assert (
        result["delivery"],
        len(api.writes),
        "pending" in json.loads((tmp_path / "state.json").read_text()),
    ) == ("deduplicated", 1, False)


def test_late_pending_confirmation_does_not_trigger_immediate_reminder(tmp_path):
    # Arrange
    api = _Cards()
    api.failure = "after-commit"
    _pass(tmp_path, api)
    api.failure = None
    # Act
    result = _pass(tmp_path, api, now=7200)
    # Assert
    assert (result["delivery"], len(api.writes)) == ("deduplicated", 1)


def test_real_nonblocking_lock_prevents_overlapping_store_calls(tmp_path):
    # Arrange
    api = _Cards()
    fd = os.open(tmp_path / "observer.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    # Act
    try:
        result = _pass(tmp_path, api)
    finally:
        os.close(fd)
    # Assert
    assert (result["delivery"], api.reads, api.writes) == ("overlap-held", 0, [])


def test_private_state_symlink_refuses_without_reading_foreign_file(tmp_path):
    # Arrange
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    foreign = tmp_path / "foreign"
    foreign.write_text("not observer state")
    (root / "state.json").symlink_to(foreign)
    api = _Cards()
    # Act
    result = _pass(root, api)
    # Assert
    assert (result["exit_code"], api.reads, api.writes, foreign.read_text()) == (
        1,
        0,
        [],
        "not observer state",
    )


def test_dry_run_has_no_state_or_sink_io(tmp_path):
    # Arrange
    root = tmp_path / "not-created"
    api = _Cards()
    # Act
    result = _pass(root, api, dry_run=True)
    # Assert
    assert (result["delivery"], root.exists(), api.reads, api.writes) == (
        "dry-run-no-write",
        False,
        0,
        [],
    )


def test_missing_card_is_created_with_exact_owner_before_comment(tmp_path):
    # Arrange
    api = _Cards()
    api.card = None
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (
        result["delivery"],
        [kind for kind, _ in api.writes],
        api.card["assignee"],
        api.card["id"],
    ) == ("alert-confirmed", ["create", "comment"], ASSIGNEE, TASK_ID)


def test_wrong_existing_card_owner_refuses_delivery(tmp_path):
    # Arrange
    api = _Cards()
    api.card["assignee"] = "foreign"
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (result["exit_code"], api.writes, result["refusal_reason"]) == (
        1,
        [],
        "policy observer Card owner/status drift",
    )


@pytest.mark.parametrize("status", ["done", "cancelled", "completed"])
def test_terminal_card_cannot_receive_observer_alert(tmp_path, status):
    # Arrange
    api = _Cards()
    api.card["status"] = status
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (result["exit_code"], api.writes, result["refusal_reason"]) == (
        1,
        [],
        "policy observer Card owner/status drift",
    )


@pytest.mark.parametrize(
    "assignee,agent",
    [(ASSIGNEE, "foreign"), ("foreign", ASSIGNEE), (ASSIGNEE, None), (None, ASSIGNEE)],
)
def test_half_owned_or_conflicting_card_cannot_receive_alert(tmp_path, assignee, agent):
    # Arrange
    api = _Cards()
    api.card.update(assignee=assignee, agent=agent)
    # Act
    result = _pass(tmp_path, api)
    # Assert
    assert (result["exit_code"], api.writes, result["refusal_reason"]) == (
        1,
        [],
        "policy observer Card owner/status drift",
    )


def test_pending_nonce_file_and_parent_are_synced_before_delivery(tmp_path):
    """Observe actual fsync calls while retaining real owned files and syscalls."""
    # Arrange
    path = tmp_path / "state.json"
    pending = {"schema": 1, "pending": {"text": "unique-delivery-fixture"}}
    events = []

    def sync(fd):
        metadata = os.fstat(fd)
        os.fsync(fd)
        if stat.S_ISDIR(metadata.st_mode):
            events.append(("directory", json.loads(path.read_text())))
        else:
            events.append(("file", None))

    real_save = _policy_observer._save_state
    observed_os = SimpleNamespace(**{**vars(os), "fsync": sync})
    save = FunctionType(real_save.__code__, {**real_save.__globals__, "os": observed_os})
    # Act
    save(path, pending)
    # Assert
    assert (events, json.loads(path.read_text()), stat.S_IMODE(path.stat().st_mode)) == (
        [("file", None), ("directory", pending)],
        pending,
        0o600,
    )
