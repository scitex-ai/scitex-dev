#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev service`` — the kind='service' CLI group.

THE BUG THIS GROUP EXISTS TO PREVENT: `sac dev systemd list` filtered
`kind="systemd"`, matched nothing, and reported "No sac systemd-kind
jobs." with exit 0 for weeks — hiding four live timers including the
fleet's sole OAuth refresher. A group whose filter can only ever return
zero jobs is indistinguishable from a healthy empty fleet, so the tests
below prove NON-EMPTY results against REAL JobSpecs, not merely exit 0.

No mocks (NM001-003): `installed_job_provider` installs a REAL
`scitex_dev.jobs` entry-point distribution on sys.path, so discovery runs
the production importlib.metadata path. Unit writes go to a REAL temp
$HOME. The "no systemd" tests set a REAL empty PATH.
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
    """Point ``$HOME`` at a temp dir; ``Path.home()`` reads it on POSIX."""
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
    """A REAL PATH with no systemctl — the nas-01 / nas-02 condition."""
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


_ARGV = ["ecosystem", "dev", "service"]


# ----------------------------------------------------------------------
# The group returns REAL jobs — the anti-"always empty" proof.
# ----------------------------------------------------------------------


def test_service_list_returns_a_real_declared_service(runner, installed_job_provider):
    # Arrange — testpkg.svc is a kind="service" JobSpec published through a
    # REAL entry point, discovered the production way.
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "testpkg.svc" in result.stdout


def test_service_list_does_not_leak_timer_kind_jobs(runner, installed_job_provider):
    # Arrange — the whole point of splitting by kind. testpkg.sysjob is a
    # kind="timer"; if it appears here the group is still mechanism-shaped.
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "testpkg.sysjob" not in result.stdout


def test_service_list_json_is_parseable_on_stdout(runner, installed_job_provider):
    # Arrange — stdout is the payload; any diagnostic on it corrupts this.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    # Assert
    assert any(j["name"] == "testpkg.svc" for j in json.loads(result.stdout))


def test_service_list_json_carries_the_restart_policy(runner, installed_job_provider):
    # Arrange — a field that APPLIES to this kind and to no other. Its
    # presence is what makes a per-kind surface worth having.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    rows = {j["name"]: j for j in json.loads(result.stdout)}
    # Assert
    assert rows["testpkg.svc"]["restart_policy"] == "on-failure"


def test_service_list_json_omits_the_timer_only_cadence_field(
    runner, installed_job_provider
):
    # Arrange — a permanent null invites a consumer to read it as data.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    rows = {j["name"]: j for j in json.loads(result.stdout)}
    # Assert
    assert "on_unit_active_sec" not in rows["testpkg.svc"]


# ----------------------------------------------------------------------
# Verb SET — a verb meaningless for this kind is absent, not erroring.
# ----------------------------------------------------------------------


def test_service_offers_the_daemon_lifecycle_verbs(runner):
    # Arrange — start/stop/restart only mean something for a daemon.
    # Act
    result = runner.invoke(main, _ARGV + ["--help"])
    # Assert
    assert all(v in result.stdout for v in ("start", "stop", "restart"))


def test_service_does_not_offer_a_timer_style_enable(runner):
    # Arrange — for a service, `[Install] WantedBy=` IS its enablement; a
    # separate `enable` verb would be a second spelling of `install` that
    # could disagree with it. ABSENT (click exit 2, "No such command"),
    # not present-and-erroring.
    # Act
    result = runner.invoke(main, _ARGV + ["enable", "testpkg.svc"])
    # Assert
    assert result.exit_code == 2


# ----------------------------------------------------------------------
# Hosts that cannot supervise: refuse, do not fail.
# ----------------------------------------------------------------------


def test_start_refuses_with_the_unsupported_exit_code(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — nas-01 / nas-02. Exit 3 is "impossible here", distinct
    # from 1 ("tried and broke") so a caller never retry-loops forever.
    # Act
    result = runner.invoke(main, _ARGV + ["start", "testpkg.svc"])
    # Assert
    assert result.exit_code == S.EXIT_UNSUPPORTED_HOST


def test_the_refusal_names_the_reason_on_stderr(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — a raw `systemctl: command not found` reads as transient.
    # Act
    result = runner.invoke(main, _ARGV + ["start", "testpkg.svc"])
    # Assert
    assert "no `systemctl` on PATH" in result.stderr


def test_the_refusal_keeps_stdout_empty(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — even a refusal must not put prose on the payload stream.
    # Act
    result = runner.invoke(main, _ARGV + ["start", "testpkg.svc"])
    # Assert
    assert result.stdout == ""


def test_start_dry_run_prints_the_command_on_a_host_without_systemd(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — CLI doctrine §2 pairs every mutating verb with --dry-run.
    # The preview must survive the host check, or an operator on a NAS
    # cannot even see what the command would be.
    # Act
    result = runner.invoke(main, _ARGV + ["start", "testpkg.svc", "--dry-run"])
    # Assert
    assert result.stdout.strip() == ("systemctl --user start testpkg.svc.service")


def test_start_dry_run_does_not_refuse(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — a preview that exits non-zero is not a preview.
    # Act
    result = runner.invoke(main, _ARGV + ["start", "testpkg.svc", "--dry-run"])
    # Assert
    assert result.exit_code == 0


def test_dry_run_install_still_works_without_systemd(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — an operator on a NAS must still be able to SEE the unit
    # text; refusing the preview too would leave them nothing to inspect.
    # Act
    result = runner.invoke(main, _ARGV + ["install", "--dry-run"])
    # Assert
    assert "Type=simple" in result.stdout


def test_status_answers_on_a_host_that_cannot_supervise(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — "there is no unit and there never can be" is the most
    # useful answer a NAS can give; refusing would leave no way to ask.
    # Act
    result = runner.invoke(main, _ARGV + ["status", "testpkg.svc", "--json"])
    # Assert
    assert json.loads(result.stdout)["host_supports_kind"] is False


def test_status_json_names_the_host_mechanism(
    runner, installed_job_provider, no_systemctl_on_path
):
    # Arrange — the caller branches on the mechanism NAME, never on prose.
    # Act
    result = runner.invoke(main, _ARGV + ["status", "testpkg.svc", "--json"])
    # Assert
    assert json.loads(result.stdout)["host_mechanism"] == "none"


# ----------------------------------------------------------------------
# install / uninstall.
# ----------------------------------------------------------------------


def test_install_without_yes_refuses(runner, installed_job_provider, temp_home):
    # Arrange
    # Act
    result = runner.invoke(main, _ARGV + ["install"])
    # Assert
    assert result.exit_code == 2


def test_install_writes_the_service_unit(runner, installed_job_provider, temp_home):
    # Arrange
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.svc", "--yes"])
    # Assert
    assert (temp_home / "testpkg.svc.service").exists()


def test_install_does_not_write_a_timer_for_a_service(
    runner, installed_job_provider, temp_home
):
    # Arrange — a service has no timer; an inert .timer file beside it
    # would be litter the operator has to clean up later.
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.svc", "--yes"])
    # Assert
    assert not (temp_home / "testpkg.svc.timer").exists()


def test_install_refuses_to_add_a_second_supervisor(
    runner, installed_job_provider, temp_home
):
    # Arrange — a hand-written unit already supervises it (sac-listen.service
    # is exactly this case, live, right now).
    temp_home.mkdir(parents=True, exist_ok=True)
    (temp_home / "testpkg.svc.service").write_text(
        "[Service]\nExecStart=/bin/true\n", encoding="utf-8"
    )
    # Act
    result = runner.invoke(main, _ARGV + ["install", "--name", "testpkg.svc", "--yes"])
    # Assert
    assert result.exit_code == S.EXIT_CONFLICTING_SUPERVISOR


def test_adopt_leaves_the_existing_unit_byte_for_byte(
    runner, installed_job_provider, temp_home
):
    # Arrange — adopting must not touch the file, or a rename/reinstall
    # silently destroys the hand-written unit's drop-ins.
    temp_home.mkdir(parents=True, exist_ok=True)
    original = "[Service]\nExecStart=/bin/true\n"
    (temp_home / "testpkg.svc.service").write_text(original, encoding="utf-8")
    # Act
    runner.invoke(
        main, _ARGV + ["install", "--name", "testpkg.svc", "--yes", "--adopt"]
    )
    # Assert
    assert (temp_home / "testpkg.svc.service").read_text() == original


def test_install_named_unknown_errors(runner, installed_job_provider):
    # Arrange — a filter that matches nothing must SAY so, not exit 0.
    # Act
    result = runner.invoke(main, _ARGV + ["install", "--name", "no.such", "--dry-run"])
    # Assert
    assert result.exit_code != 0


def test_uninstall_removes_the_unit(runner, installed_job_provider, temp_home):
    # Arrange
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.svc", "--yes"])
    # Act
    runner.invoke(main, _ARGV + ["uninstall", "--name", "testpkg.svc", "--yes"])
    # Assert
    assert not (temp_home / "testpkg.svc.service").exists()


def test_uninstall_without_yes_refuses(runner, installed_job_provider, temp_home):
    # Arrange
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.svc", "--yes"])
    # Act
    result = runner.invoke(main, _ARGV + ["uninstall", "--name", "testpkg.svc"])
    # Assert
    assert result.exit_code == 2


# EOF
