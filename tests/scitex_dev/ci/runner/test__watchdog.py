"""Tests for the tri-state runner watchdog.

Mirrors ``src/scitex_dev/ci/runner/_watchdog.py`` (PS-204 §2 test-file mirroring).

The star is the PURE ``assess_runner_health`` — a tri-state (up / wedged /
unknown) decision with NO I/O, so it needs no mocks. The core invariant under
test: a probe that could NOT observe the fleet yields ``unknown`` and NEVER
``up`` — silent absence must not masquerade as health. The output-adapter
helpers and the stuck-run age maths are covered with real dict / timestamp
inputs (no network). One assertion per test (STX-TQ007); AAA markers
(STX-TQ002).
"""

from __future__ import annotations

import datetime as dt

from scitex_dev.ci.runner._watchdog import (
    HealthReport,
    RunnerState,
    _lease_running_from_status,
    _online_labels_from_runner_status,
    assess_runner_health,
    max_age_min,
)

_HEALTHY_KW = dict(
    runner_query_ok=True,
    online_labels=[["self-hosted", "Linux", "X64", "scitex-ci"]],
    lease_query_ok=True,
    lease_running=True,
    inflight_query_ok=True,
    oldest_unprocessed_min=None,
    want_label="scitex-ci",
    stuck_grace_min=15.0,
)


# ---------------------------------------------------------------------------
# assess_runner_health — UP
# ---------------------------------------------------------------------------


def test_online_runner_running_lease_and_no_stuck_run_is_up():
    # Arrange
    kw = dict(_HEALTHY_KW)
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.UP


def test_up_report_is_healthy_and_exits_zero():
    # Arrange
    kw = dict(_HEALTHY_KW)
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert (report.healthy, report.exit_code) == (True, 0)


# ---------------------------------------------------------------------------
# assess_runner_health — WEDGED (observed, not processing)
# ---------------------------------------------------------------------------


def test_stuck_run_past_grace_is_wedged():
    # Arrange — a run has sat at conclusion=None for 40min ≥ 15min grace.
    kw = {**_HEALTHY_KW, "oldest_unprocessed_min": 40.0}
    # Act
    report = assess_runner_health(**kw)
    # Assert — the live-incident signal: registered but not processing.
    assert report.state is RunnerState.WEDGED


def test_stuck_run_within_grace_is_still_up():
    # Arrange — a fresh unprocessed run (3min) is not yet wedged.
    kw = {**_HEALTHY_KW, "oldest_unprocessed_min": 3.0}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.UP


def test_no_matching_online_runner_is_wedged():
    # Arrange — an online runner exists but not carrying the wanted label.
    kw = {**_HEALTHY_KW, "online_labels": [["self-hosted", "other-label"]]}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.WEDGED


def test_missing_lease_is_wedged():
    # Arrange
    kw = {**_HEALTHY_KW, "lease_running": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.WEDGED


def test_wedged_report_exits_nonzero():
    # Arrange
    kw = {**_HEALTHY_KW, "lease_running": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert (report.healthy, report.exit_code) == (False, 1)


def test_wedged_reasons_name_the_stuck_run():
    # Arrange
    kw = {**_HEALTHY_KW, "oldest_unprocessed_min": 99.0}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert any("conclusion=None" in r for r in report.reasons)


# ---------------------------------------------------------------------------
# assess_runner_health — UNKNOWN (can't tell → NEVER up)
# ---------------------------------------------------------------------------


def test_failed_runner_probe_is_unknown_not_up():
    # Arrange — the runners probe failed; every other signal looks healthy.
    kw = {**_HEALTHY_KW, "runner_query_ok": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert — the core honesty rule: can't-tell must not become "up".
    assert report.state is RunnerState.UNKNOWN


def test_failed_lease_probe_is_unknown():
    # Arrange
    kw = {**_HEALTHY_KW, "lease_query_ok": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.UNKNOWN


def test_failed_inflight_probe_is_unknown():
    # Arrange
    kw = {**_HEALTHY_KW, "inflight_query_ok": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.UNKNOWN


def test_unknown_report_exits_nonzero():
    # Arrange
    kw = {**_HEALTHY_KW, "runner_query_ok": False}
    # Act
    report = assess_runner_health(**kw)
    # Assert — unknown fails loud, exactly like wedged.
    assert (report.healthy, report.exit_code) == (False, 1)


def test_unknown_takes_precedence_over_observed_problems():
    # Arrange — a probe failed AND the observed signals are bad; unknown wins
    # because we cannot trust a partial view.
    kw = {
        **_HEALTHY_KW,
        "runner_query_ok": False,
        "lease_running": False,
        "online_labels": [],
    }
    # Act
    report = assess_runner_health(**kw)
    # Assert
    assert report.state is RunnerState.UNKNOWN


# ---------------------------------------------------------------------------
# HealthReport.to_dict — JSON-serialisable shape
# ---------------------------------------------------------------------------


def test_to_dict_serialises_state_as_plain_string():
    # Arrange
    report = HealthReport(RunnerState.WEDGED, ["boom"])
    # Act
    payload = report.to_dict()
    # Assert
    assert payload == {"state": "wedged", "healthy": False, "reasons": ["boom"]}


# ---------------------------------------------------------------------------
# _online_labels_from_runner_status — adapt _status output honestly
# ---------------------------------------------------------------------------


def test_runner_status_error_reports_query_not_ok():
    # Arrange — a gh api error must map to query_ok=False (→ unknown upstream).
    rstat = {"error": "gh api boom"}
    # Act
    ok, _labels = _online_labels_from_runner_status(rstat)
    # Assert
    assert ok is False


def test_runner_status_keeps_only_online_runner_labels():
    # Arrange — one online, one offline runner.
    rstat = {
        "runners": [
            {"status": "online", "labels": ["self-hosted", "scitex-ci"]},
            {"status": "offline", "labels": ["self-hosted", "scitex-ci"]},
        ]
    }
    # Act
    ok, labels = _online_labels_from_runner_status(rstat)
    # Assert
    assert (ok, labels) == (True, [["self-hosted", "scitex-ci"]])


# ---------------------------------------------------------------------------
# _lease_running_from_status
# ---------------------------------------------------------------------------


def test_lease_error_reports_query_not_ok():
    # Arrange
    lease = {"error": "squeue over ssh failed"}
    # Act
    ok, running = _lease_running_from_status(lease)
    # Assert
    assert (ok, running) == (False, False)


def test_lease_running_when_a_running_job_present():
    # Arrange
    lease = {"jobs": [{"state": "PENDING"}, {"state": "RUNNING"}]}
    # Act
    ok, running = _lease_running_from_status(lease)
    # Assert
    assert (ok, running) == (True, True)


# ---------------------------------------------------------------------------
# max_age_min — pure stuck-run maths
# ---------------------------------------------------------------------------


def test_max_age_min_empty_is_none():
    # Arrange
    stamps: list[str] = []
    # Act
    result = max_age_min(stamps)
    # Assert — no unprocessed runs → nothing stuck.
    assert result is None


def test_max_age_min_returns_oldest_in_minutes():
    # Arrange — now anchored; oldest stamp is 30min back.
    now = dt.datetime(2026, 7, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
    stamps = ["2026-07-18T11:30:00Z", "2026-07-18T11:50:00Z"]
    # Act
    result = max_age_min(stamps, now=now)
    # Assert
    assert result == 30.0


# EOF
