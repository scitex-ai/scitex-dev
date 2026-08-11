#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev timer`` — the kind='timer' CLI group.

The kind that the old mechanism-shaped `systemd` group hid. `sac dev
systemd list` filtered `kind="systemd"` — a value the JobSpec validator
REJECTS — matched nothing, and printed "No sac systemd-kind jobs." with
exit 0 while four timers ran, including `sac.accounts-refresh`, the
fleet's sole OAuth refresher.

So these tests prove NON-EMPTY results against REAL JobSpecs: the
scitex-dev built-in `ecosystem-self-pull` (always present, no external
package required) plus `testpkg.sysjob` from a REAL installed entry point.

No mocks (NM001-003).
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli.ecosystem._cmds import _jobs_supervision as S


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_home(tmp_path):
    prev = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path / ".config" / "systemd" / "user"
    finally:
        if prev is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prev


@pytest.fixture
def no_systemctl_on_path(tmp_path):
    empty = tmp_path / "emptybin"
    empty.mkdir()
    prev = os.environ.get("PATH")
    os.environ["PATH"] = str(empty)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = prev


_ARGV = ["ecosystem", "dev", "timer"]


# ----------------------------------------------------------------------
# The group returns REAL jobs — the anti-"always empty" proof.
# ----------------------------------------------------------------------


def test_timer_list_returns_the_builtin_self_pull_timer(runner):
    # Arrange — a scitex-dev BUILT-IN kind="timer" job, present with no
    # external package installed. If this group could only ever be empty,
    # this assertion is the one that fails.
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "ecosystem-self-pull" in result.stdout


def test_timer_list_returns_a_provider_declared_timer(runner, installed_job_provider):
    # Arrange — the federated half, through a REAL entry point.
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "testpkg.sysjob" in result.stdout


def test_timer_list_does_not_leak_service_kind_jobs(runner, installed_job_provider):
    # Arrange — the split is the point; testpkg.svc is kind="service".
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "testpkg.svc" not in result.stdout


def test_timer_list_json_is_parseable_on_stdout(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    # Assert
    assert any(j["name"] == "testpkg.sysjob" for j in json.loads(result.stdout))


def test_timer_list_json_carries_the_cadence(runner, installed_job_provider):
    # Arrange — the field that APPLIES to this kind and to no other.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    rows = {j["name"]: j for j in json.loads(result.stdout)}
    # Assert
    assert rows["testpkg.sysjob"]["on_unit_active_sec"] == "4h"


def test_timer_list_json_omits_the_service_only_restart_policy(
    runner, installed_job_provider
):
    # Arrange — a timer MUST have restart_policy="no"; emitting it would
    # invite a consumer to read a constant as a decision.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    rows = {j["name"]: j for j in json.loads(result.stdout)}
    # Assert
    assert "restart_policy" not in rows["testpkg.sysjob"]


# ----------------------------------------------------------------------
# Verb SET — meaningless verbs are ABSENT, not present-and-erroring.
# ----------------------------------------------------------------------


def test_timer_offers_enable_and_disable(runner):
    # Arrange — a timer's real lifecycle: the unit persists, enablement
    # decides whether it fires.
    # Act
    result = runner.invoke(main, _ARGV + ["--help"])
    # Assert
    assert "enable" in result.stdout and "disable" in result.stdout


def test_timer_does_not_offer_restart(runner):
    # Arrange — `systemctl restart foo.timer` restarts the TIMER, not the
    # job. An operator reaching for it means "run the body now", which is
    # `ecosystem dev cron exec`. A verb that does the other thing is worse
    # than no verb, so it must be ABSENT (click exit 2, "No such command")
    # rather than present-and-erroring.
    # Act
    result = runner.invoke(main, _ARGV + ["restart", "testpkg.sysjob"])
    # Assert
    assert result.exit_code == 2


# ----------------------------------------------------------------------
# Hosts that cannot supervise.
# ----------------------------------------------------------------------


def test_enable_refuses_with_the_unsupported_exit_code(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — three of nine fleet hosts.
    # Act
    result = runner.invoke(main, _ARGV + ["enable", "testpkg.sysjob"])
    # Assert
    assert result.exit_code == S.EXIT_UNSUPPORTED_HOST


def test_enable_dry_run_prints_the_command_with_the_now_flag(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — CLI doctrine §2 pairs every mutating verb with --dry-run.
    # `--now` is what makes enable also START the timer, so a preview that
    # omitted it would understate what the command does.
    # Act
    result = runner.invoke(main, _ARGV + ["enable", "testpkg.sysjob", "--dry-run"])
    # Assert
    assert result.stdout.strip() == (
        "systemctl --user enable --now testpkg.sysjob.timer"
    )


def test_disable_dry_run_does_not_touch_the_fleets_sole_refresher(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — `disable sac.accounts-refresh` stops the fleet's SOLE OAuth
    # refresher and every account expires within one access-token lifetime.
    # A preview must therefore be genuinely inert AND exit 0.
    # Act
    result = runner.invoke(main, _ARGV + ["disable", "testpkg.sysjob", "--dry-run"])
    # Assert
    assert result.exit_code == 0


def test_the_refusal_points_at_cron_as_the_universal_mechanism(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — nas-01/-02 have a working crontab binary; saying so turns
    # a dead end into a next step.
    # Act
    result = runner.invoke(main, _ARGV + ["enable", "testpkg.sysjob"])
    # Assert
    assert "kind='cron'" in result.stderr


# ----------------------------------------------------------------------
# install / uninstall — BOTH unit files.
# ----------------------------------------------------------------------


def test_install_writes_the_timer_unit(runner, installed_job_provider, temp_home):
    # Arrange
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert (temp_home / "testpkg.sysjob.timer").exists()


def test_install_writes_the_oneshot_service_too(
    runner, installed_job_provider, temp_home
):
    # Arrange — a timer fires a service; writing only the .timer leaves it
    # pointing at nothing.
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert (temp_home / "testpkg.sysjob.service").exists()


def test_the_written_timer_is_persistent(runner, installed_job_provider, temp_home):
    # Arrange — Persistent=true is what makes a missed tick catch up.
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert "Persistent=true" in (temp_home / "testpkg.sysjob.timer").read_text()


def test_install_refuses_to_add_a_second_supervisor(
    runner, installed_job_provider, temp_home
):
    # Arrange — sac.accounts-refresh is the fleet's SOLE OAuth refresher
    # and its refresh token is SINGLE-USE: two racing refreshers revoke
    # each other and expire every account within hours.
    temp_home.mkdir(parents=True, exist_ok=True)
    (temp_home / "testpkg.sysjob.timer").write_text(
        "[Timer]\nOnUnitActiveSec=4h\n", encoding="utf-8"
    )
    # Act
    result = runner.invoke(
        main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"]
    )
    # Assert
    assert result.exit_code == S.EXIT_CONFLICTING_SUPERVISOR


def test_uninstall_removes_both_units(runner, installed_job_provider, temp_home):
    # Arrange
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Act
    runner.invoke(main, _ARGV + ["uninstall", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert not any(
        (temp_home / f"testpkg.sysjob{s}").exists() for s in (".service", ".timer")
    )


# EOF
