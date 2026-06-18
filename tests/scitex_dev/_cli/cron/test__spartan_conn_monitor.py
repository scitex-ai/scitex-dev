#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ``spartan-conn-monitor`` cron body — no mocks.

The ssh boundary and the notification/phone-call boundaries are injected as
plain fakes (Callables), per PA-306 / STX-NM*. One assertion per test, AAA
markers throughout.
"""

from __future__ import annotations

import io

import pytest

from scitex_dev._cli.cron import _spartan_conn_monitor as mon


# -- pure helpers -----------------------------------------------------------


def test_parse_returns_four_ints():
    # Arrange
    line = "0 2 92 78\n"
    # Act
    parsed = mon._parse(line)
    # Assert
    assert parsed == (0, 2, 92, 78)


def test_parse_rejects_wrong_field_count():
    # Arrange
    line = "0 2 92\n"
    # Act
    parsed = mon._parse(line)
    # Assert
    assert parsed is None


def test_parse_rejects_non_numeric():
    # Arrange
    line = "x y z w\n"
    # Act
    parsed = mon._parse(line)
    # Assert
    assert parsed is None


def test_thresholds_clean_reading_has_no_alerts():
    # Arrange — srun under the new SRUN_MAX so a healthy node stays quiet.
    r = mon.NodeReading("spartan-login1.x", 0, 2, 92, 5, reachable=True)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert alerts == []


def test_thresholds_flag_excess_ssh_agents():
    # Arrange
    r = mon.NodeReading("spartan-login2.x", 99, 0, 7, 0, reachable=True)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert any("ssh-agents=99" in a for a in alerts)


def test_thresholds_flag_excess_srun_clients():
    # Arrange — per-node srun client ceiling (the SSH-vector early warning).
    r = mon.NodeReading("spartan-login2.x", 0, 0, 80, 76, reachable=True)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert any("srun=76" in a for a in alerts)


def test_thresholds_srun_at_ceiling_is_quiet():
    # Arrange — exactly SRUN_MAX is within bounds (alert is strictly >).
    r = mon.NodeReading("spartan-login3.x", 0, 0, 60, mon.SRUN_MAX, reachable=True)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert not any("srun=" in a for a in alerts)


def test_thresholds_flag_extreme_proc_count():
    # Arrange
    r = mon.NodeReading("spartan-login3.x", 0, 0, 999, 10, reachable=True)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert any("procs=999" in a for a in alerts)


def test_thresholds_ignore_unreachable_node():
    # Arrange
    r = mon.NodeReading("spartan-login1.x", None, None, None, None, reachable=False)
    # Act
    alerts = mon._check_thresholds(r)
    # Assert
    assert alerts == []


# -- run_once (injected fakes) ----------------------------------------------


@pytest.fixture
def healthy_run(tmp_path):
    """All nodes clean → no alert; TSV written; no call placed.

    srun=4 is healthy under the new SRUN_MAX (the SSH-vector launch fix keeps
    per-node srun near zero); agents=0, procs=90 are both well within bounds.
    """
    calls = []
    notes = []
    res = mon.run_once(
        ssh_runner=lambda node: (0, "0 1 90 4\n"),
        notifier=lambda m: notes.append(m),
        caller=lambda m: calls.append(m),
        now=lambda: "2026-06-17T16:00:00",
        path=tmp_path / "m.tsv",
        out=io.StringIO(),
    )
    return {"res": res, "calls": calls, "notes": notes, "tsv": tmp_path / "m.tsv"}


def test_healthy_run_raises_no_alert(healthy_run):
    # Arrange
    res = healthy_run["res"]
    # Act
    alerts = res.alerts
    # Assert
    assert alerts == []


def test_healthy_run_places_no_phone_call(healthy_run):
    # Arrange
    # Act
    calls = healthy_run["calls"]
    # Assert
    assert calls == []


def test_healthy_run_writes_a_row_per_node(healthy_run):
    # Arrange
    text = healthy_run["tsv"].read_text(encoding="utf-8")
    # Act — header + 3 node rows.
    data_rows = [
        ln for ln in text.splitlines() if ln and not ln.startswith("timestamp")
    ]
    # Assert
    assert len(data_rows) == len(mon.LOGIN_NODES)


@pytest.fixture
def breach_run(tmp_path):
    """ssh-agents over threshold on every node → alert + phone call."""
    calls = []
    res = mon.run_once(
        ssh_runner=lambda node: (0, "40 0 100 50\n"),
        notifier=lambda m: None,
        caller=lambda m: calls.append(m),
        now=lambda: "2026-06-17T16:00:00",
        path=tmp_path / "m.tsv",
        out=io.StringIO(),
    )
    return {"res": res, "calls": calls}


def test_breach_run_raises_alerts(breach_run):
    # Arrange
    # Act
    res = breach_run["res"]
    # Assert
    assert len(res.alerts) >= 1


def test_breach_run_places_a_phone_call(breach_run):
    # Arrange
    # Act — exactly one combined call, not one per node.
    calls = breach_run["calls"]
    # Assert
    assert len(calls) == 1


@pytest.fixture
def srun_only_breach(tmp_path):
    """agents/procs clean, srun ALONE over the ceiling on every node."""
    calls = []
    res = mon.run_once(
        ssh_runner=lambda node: (0, f"0 0 80 {mon.SRUN_MAX + 1}\n"),
        notifier=lambda m: None,
        caller=lambda m: calls.append(m),
        now=lambda: "2026-06-17T16:00:00",
        path=tmp_path / "m.tsv",
        out=io.StringIO(),
    )
    return {"res": res, "calls": calls}


def test_srun_only_breach_raises_alerts(srun_only_breach):
    # Arrange
    # Act
    res = srun_only_breach["res"]
    # Assert — the srun threshold alone is enough to flag a regression.
    assert len(res.alerts) >= 1


def test_srun_only_breach_places_a_phone_call(srun_only_breach):
    # Arrange
    # Act
    calls = srun_only_breach["calls"]
    # Assert
    assert len(calls) == 1


def test_unreachable_node_is_recorded_not_crashed(tmp_path):
    # Arrange — ssh fails (rc!=0) for every node.
    res = mon.run_once(
        ssh_runner=lambda node: (255, ""),
        notifier=lambda m: None,
        caller=lambda m: None,
        now=lambda: "2026-06-17T16:00:00",
        path=tmp_path / "m.tsv",
        out=io.StringIO(),
    )
    # Act
    unreachable = [r for r in res.readings if not r.reachable]
    # Assert
    assert len(unreachable) == len(mon.LOGIN_NODES)
