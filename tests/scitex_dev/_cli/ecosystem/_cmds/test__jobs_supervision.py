#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host-capability probe + mechanism-blind supervisor scan.

Measured fleet inventory (2026-08-11) that these tests encode: three of
nine hosts cannot run a kind='service'/'timer' job AT ALL — mba is
macOS/launchd, and scitex-nas-01 (Synology, armv7l) and scitex-nas-02
(QNAP) answer `systemctl: command not found`. So the refusal path is the
COMMON case for part of the fleet, not an edge case.

No mocks, no monkeypatch (NM001-003): the "no systemctl" fixture sets a
REAL empty PATH through os.environ so the real `shutil.which` really
fails, the unit scan reads REAL files under tmp_path, and the crontab scan
is fed the REAL line measured on the head node.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev._cli.ecosystem._cmds import _jobs_supervision as S
from scitex_dev.jobs import JobSpec

#: The line measured LIVE on the head node, verbatim. A crontab watchdog
#: supervising the same process as `sac-listen.service`. It names the
#: SCRIPT, not the JobSpec, which is why an exact-name search misses it.
_LIVE_CONFLICTING_CRON_LINE = (
    "*/2 * * * * ~/.scitex/agent-container/bin/sac-listen-watch.sh "
    "# sac-listen-supervisor"
)


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


def _service_job(name="sac.listen"):
    return JobSpec(
        name=name,
        kind="service",
        schedule="",
        command="sac listen",
        description="listener",
        restart_policy="on-failure",
    )


def _exit_code_of(call) -> object:
    """Return the SystemExit code ``call`` raises, or ``None`` if it does not.

    Lets a test assert the CODE in one assertion. `pytest.raises` plus a
    second assert would be two, and the first failure would hide the
    second — which for an exit code is the half that matters.
    """
    try:
        call()
    except SystemExit as exc:
        return exc.code
    return None


def test_macos_is_reported_as_launchd_not_as_a_broken_host():
    # Arrange — mba. Naming launchd is the difference between "this host
    # uses another mechanism" and "this host is broken".
    # Act
    sup = S.probe_supervision(platform="darwin")
    # Assert
    assert sup.mechanism == "launchd"


def test_macos_is_not_available_for_systemd_kinds():
    # Arrange
    # Act
    sup = S.probe_supervision(platform="darwin")
    # Assert
    assert sup.available is False


def test_a_host_without_systemctl_is_unavailable(no_systemctl_on_path):
    # Arrange — REAL empty PATH, REAL shutil.which. nas-01 / nas-02.
    # Act
    sup = S.probe_supervision(platform="linux")
    # Assert
    assert sup.available is False


def test_the_refusal_reason_names_the_missing_binary(no_systemctl_on_path):
    # Arrange — a reason that does not say WHAT is missing leaves the
    # operator with the same lookup that produced the confusion.
    # Act
    sup = S.probe_supervision(platform="linux")
    # Assert
    assert "systemctl" in sup.reason


def test_the_remedy_points_at_the_one_mechanism_that_works_everywhere(
    no_systemctl_on_path,
):
    # Arrange — cron is the only fleet-wide option; leaving that to be
    # rediscovered per host is how the same outage recurs.
    # Act
    sup = S.probe_supervision(platform="linux")
    # Assert
    assert "kind='cron'" in sup.remedy


def test_require_supervision_exits_with_the_unsupported_code(
    no_systemctl_on_path,
):
    # Arrange — the caller must distinguish "impossible here" from
    # "tried and failed"; exit 1 would conflate them.
    sup = S.probe_supervision(platform="linux")
    # Act
    code = _exit_code_of(lambda: S.require_supervision("service", "start", sup))
    # Assert
    assert code == S.EXIT_UNSUPPORTED_HOST


def test_require_supervision_is_a_noop_when_the_host_can_help():
    # Arrange — POSITIVE CONTROL: the guard must not refuse everywhere,
    # or every test above would pass on a guard that never lets anything
    # through.
    sup = S.Supervision(True, "systemd-user", "reachable", "")
    # Act
    result = S.require_supervision("service", "start", sup)
    # Assert
    assert result is None


# ----------------------------------------------------------------------
# Mechanism-blind supervisor scan.
# ----------------------------------------------------------------------


def test_a_foreign_unit_file_is_found(tmp_path):
    # Arrange — sac-listen.service is HAND-WRITTEN and live right now.
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "sac.listen.service").write_text(
        "[Service]\nExecStart=/usr/bin/sac listen\n", encoding="utf-8"
    )
    # Act
    found = S.find_supervisors(_service_job(), home=tmp_path, crontab_text="")
    # Assert
    assert [s.mechanism for s in found] == ["systemd-unit"]


def test_a_hand_written_unit_is_not_claimed_as_ours(tmp_path):
    # Arrange — overwriting a unit we did not write destroys its drop-ins.
    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "sac.listen.service").write_text(
        "[Service]\nExecStart=/usr/bin/sac listen\n", encoding="utf-8"
    )
    # Act
    found = S.find_supervisors(_service_job(), home=tmp_path, crontab_text="")
    # Assert
    assert found[0].ours is False


def test_our_own_unit_is_recognised_by_its_documentation_marker(tmp_path):
    # Arrange — POSITIVE CONTROL for the ownership test above.
    from scitex_dev.jobs import _systemd as sd

    unit_dir = tmp_path / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    job = _service_job()
    (unit_dir / "sac.listen.service").write_text(
        sd.build_service_unit(job), encoding="utf-8"
    )
    # Act
    found = S.find_supervisors(job, home=tmp_path, crontab_text="")
    # Assert
    assert found[0].ours is True


def test_the_live_crontab_watchdog_is_found(tmp_path):
    # Arrange — THE case that motivated a mechanism-blind scan. This exact
    # line runs on the head node beside sac-listen.service; a unit-only
    # check saw nothing and would have installed a third supervisor.
    # Act
    found = S.find_supervisors(
        _service_job(),
        home=tmp_path,
        crontab_text=_LIVE_CONFLICTING_CRON_LINE + "\n",
    )
    # Assert
    assert [s.mechanism for s in found] == ["crontab"]


def test_an_unrelated_crontab_line_is_not_claimed(tmp_path):
    # Arrange — POSITIVE CONTROL: a scan that matched everything would
    # make install refuse forever, which is its own outage.
    # Act
    found = S.find_supervisors(
        _service_job(),
        home=tmp_path,
        crontab_text="0 3 * * * /usr/bin/backup.sh # nightly-backup\n",
    )
    # Assert
    assert found == []


def test_a_commented_out_crontab_line_does_not_count(tmp_path):
    # Arrange — a parked line supervises nothing, so treating it as a
    # conflict would block a legitimate install.
    # Act
    found = S.find_supervisors(
        _service_job(),
        home=tmp_path,
        crontab_text="#" + _LIVE_CONFLICTING_CRON_LINE + "\n",
    )
    # Assert
    assert found == []


def test_install_refuses_when_something_already_supervises(tmp_path):
    # Arrange — the default must be the safe one. sac.accounts-refresh is
    # the fleet's SOLE OAuth refresher with a SINGLE-USE refresh token:
    # two racing refreshers revoke each other and expire every account.
    # Act
    code = _exit_code_of(
        lambda: S.guard_existing_supervisors(
            _service_job(),
            adopt=False,
            force=False,
            home=tmp_path,
            crontab_text=_LIVE_CONFLICTING_CRON_LINE + "\n",
        )
    )
    # Assert
    assert code == S.EXIT_CONFLICTING_SUPERVISOR


def test_adopt_declines_to_write_over_an_existing_supervisor(tmp_path):
    # Arrange — adopt means "that one is THE supervisor"; writing a second
    # unit beside it is exactly what adoption is meant to prevent.
    # Act
    proceed = S.guard_existing_supervisors(
        _service_job(),
        adopt=True,
        force=False,
        home=tmp_path,
        crontab_text=_LIVE_CONFLICTING_CRON_LINE + "\n",
    )
    # Assert
    assert proceed is False


def test_force_proceeds_over_an_existing_supervisor(tmp_path):
    # Arrange — the deliberate operator override still has to exist, or
    # a genuinely stale unit can never be replaced.
    # Act
    proceed = S.guard_existing_supervisors(
        _service_job(),
        adopt=False,
        force=True,
        home=tmp_path,
        crontab_text=_LIVE_CONFLICTING_CRON_LINE + "\n",
    )
    # Assert
    assert proceed is True


def test_an_unsupervised_job_proceeds_without_flags(tmp_path):
    # Arrange — POSITIVE CONTROL: the guard must not block the clean case.
    # Act
    proceed = S.guard_existing_supervisors(
        _service_job(),
        adopt=False,
        force=False,
        home=tmp_path,
        crontab_text="",
    )
    # Assert
    assert proceed is True


# EOF
