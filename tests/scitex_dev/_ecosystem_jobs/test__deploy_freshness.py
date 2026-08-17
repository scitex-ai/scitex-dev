"""Unit tests for the ``deploy-freshness`` cron body.

Real fakes only (PA-306 / STX-NM). Every external seam
(``http_runner``, ``pip_runner``, ``systemctl_runner``, ``which``,
``metadata_lookup``, ``jobs_provider``, ``log_path``, ``now``) is a
keyword argument on :func:`run_once` and :func:`check_one_service`,
so tests pass hand-rolled callables and ``tmp_path``-rooted files
without ``unittest.mock`` or ``monkeypatch``.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scitex_dev._ecosystem_jobs import _deploy_freshness as df
from scitex_dev.jobs import JobSpec


# --------------------------------------------------------------------- #
# Real-fake builders                                                    #
# --------------------------------------------------------------------- #


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr
    )


def _ok_pip(args):
    return _completed(rc=0)


def _ok_sysctl(args, **_):
    return _completed(rc=0)


def _http_returning_version(version: str):
    """HTTP runner that returns a PyPI JSON body with ``info.version = version``."""
    import json

    body = json.dumps({"info": {"version": version}}).encode("utf-8")

    def runner(url: str, timeout: float):
        return 200, body

    return runner


def _http_503():
    def runner(url: str, timeout: float):
        return 503, b""

    return runner


def _metadata_lookup_returning(binary_name: str, dist_name: str, version: str):
    """Real fake for ``importlib.metadata.entry_points`` (group filter)."""

    class _Dist:
        def __init__(self, name, ver):
            self._name = name
            self.version = ver

        @property
        def metadata(self):
            return {"Name": self._name}

    class _EP:
        def __init__(self, name, dist):
            self.name = name
            self.group = "console_scripts"
            self.dist = dist

    eps = [_EP(binary_name, _Dist(dist_name, version))]

    def lookup(*, group=None):
        if group is None or group == "console_scripts":
            return eps
        return []

    return lookup


def _no_metadata():
    def lookup(*, group=None):
        return []

    return lookup


def _job_service(name="scitex-todo.dashboard", command="scitex-todo board --port 8051"):
    return JobSpec(
        name=name,
        kind="service",
        schedule="",
        command=command,
        description="d",
        on_boot_sec="15s",
        restart_policy="on-failure",
        timeout_sec=30,
    )


# --------------------------------------------------------------------- #
# Editable-path real fakes                                             #
# --------------------------------------------------------------------- #


def _editable_direct_url(srcdir: str = "/home/op/proj/scitex-todo"):
    """direct_url_lookup fake: PEP 610 EDITABLE install rooted at srcdir."""
    import json

    text = json.dumps({"url": f"file://{srcdir}", "dir_info": {"editable": True}})

    def lookup(dist_name: str):
        return text

    return lookup


def _wheel_direct_url():
    """direct_url_lookup fake: a plain wheel install (no direct_url.json)."""

    def lookup(dist_name: str):
        return None

    return lookup


def _git_returning(iso: str):
    """git_runner fake returning a fixed `%cI`-style ISO commit time."""

    def runner(srcdir: str):
        return iso

    return runner


def _git_not_a_repo():
    """git_runner fake for a source dir that is not a git work tree."""

    def runner(srcdir: str):
        return None

    return runner


def _no_source_mtime():
    def runner(srcdir: str):
        return None

    return runner


def _systemctl_active_at(timestamp_value: str):
    """systemctl_runner fake.

    Answers `show -p ActiveEnterTimestamp` with the supplied value and
    records every `restart` call in the returned ``.restart_calls`` list,
    so a single fake covers both the read and the repair in one test.
    """
    restart_calls: list = []

    def runner(args, **_):
        if args[:1] == ["show"]:
            return _completed(rc=0, stdout=f"ActiveEnterTimestamp={timestamp_value}\n")
        if args[:1] == ["restart"]:
            restart_calls.append(args)
            return _completed(rc=0)
        return _completed(rc=0)

    runner.restart_calls = restart_calls
    return runner


# --------------------------------------------------------------------- #
# Pure helpers                                                          #
# --------------------------------------------------------------------- #


def test_extract_binary_returns_first_token():
    # Arrange
    # Act
    binary = df._extract_binary("scitex-todo board --port 8051")
    # Assert
    assert binary == "scitex-todo"


def test_extract_binary_returns_none_for_empty_command():
    # Arrange
    # Act
    binary = df._extract_binary("")
    # Assert
    assert binary is None


def test_extract_binary_handles_absolute_paths():
    # Arrange
    # Act
    binary = df._extract_binary("/home/op/.env/bin/scitex-todo board")
    # Assert
    assert binary == "/home/op/.env/bin/scitex-todo"


def test_binary_basename_strips_path():
    # Arrange
    # Act
    name = df._binary_basename("/home/op/.env/bin/scitex-todo")
    # Assert
    assert name == "scitex-todo"


def test_version_tuple_parses_semver_dotted():
    # Arrange
    # Act
    parts = df._version_tuple("0.17.12")
    # Assert
    assert parts == (0, 17, 12)


def test_version_tuple_returns_empty_for_garbage():
    # Arrange
    # Act
    parts = df._version_tuple("")
    # Assert
    assert parts == ()


def test_is_drifted_returns_true_when_installed_lower():
    # Arrange
    # Act
    drifted = df._is_drifted("0.5.2", "0.5.3")
    # Assert
    assert drifted is True


def test_is_drifted_returns_false_when_versions_equal():
    # Arrange
    # Act
    drifted = df._is_drifted("0.17.12", "0.17.12")
    # Assert
    assert drifted is False


def test_is_drifted_returns_false_when_installed_higher():
    # Arrange
    # Act
    drifted = df._is_drifted("0.17.12", "0.17.11")
    # Assert
    assert drifted is False


def test_is_drifted_returns_false_when_either_unparseable():
    # Arrange
    # Act
    drifted = df._is_drifted("garbage", "0.17.12")
    # Assert
    assert drifted is False


def test_fetch_latest_pypi_version_returns_info_version():
    # Arrange
    runner = _http_returning_version("0.17.12")
    # Act
    latest = df._fetch_latest_pypi_version("scitex-dev", http_runner=runner)
    # Assert
    assert latest == "0.17.12"


def test_fetch_latest_pypi_version_returns_none_on_503():
    # Arrange
    runner = _http_503()
    # Act
    latest = df._fetch_latest_pypi_version("scitex-dev", http_runner=runner)
    # Assert
    assert latest is None


# --------------------------------------------------------------------- #
# check_one_service                                                     #
# --------------------------------------------------------------------- #


def test_check_one_service_returns_ok_when_no_drift():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.3"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.action == "ok"


def test_check_one_service_drift_detected_returns_would_update_in_dry_run():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.action == "would-update"


def test_check_one_service_drift_reports_drift_true():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.drift is True


def test_check_one_service_unknown_binary_returns_skipped():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_no_metadata(),
    )
    # Assert
    assert outcome.action == "skipped"


def test_check_one_service_pypi_unreachable_returns_skipped():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_503(),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.action == "skipped"


def test_check_one_service_apply_runs_pip_install_dash_u():
    # Arrange
    job = _job_service()
    pip_calls = []

    def pip(args):
        pip_calls.append(args)
        return _completed(rc=0)

    # Act
    df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=pip,
        systemctl_runner=_ok_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert
    assert pip_calls == [["install", "-U", "scitex-todo"]]


def test_check_one_service_apply_restarts_systemd_unit():
    # Arrange
    job = _job_service()
    sysctl_calls = []

    def sysctl(args, **_):
        sysctl_calls.append(args)
        return _completed(rc=0)

    # Act
    df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=_ok_pip,
        systemctl_runner=sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert — service kind → unit name is <name>.service
    assert sysctl_calls == [["restart", "scitex-todo.dashboard.service"]]


def test_check_one_service_apply_returns_updated_on_clean_path():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=_ok_pip,
        systemctl_runner=_ok_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert
    assert outcome.action == "updated"


def test_check_one_service_apply_returns_error_when_pip_missing():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=_ok_pip,
        systemctl_runner=_ok_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda _n: None,  # pip not on PATH
    )
    # Assert
    assert outcome.action == "error"


def test_check_one_service_apply_returns_error_when_pip_fails():
    # Arrange
    job = _job_service()

    def failing_pip(args):
        return _completed(rc=1, stderr="resolve failure")

    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=failing_pip,
        systemctl_runner=_ok_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert
    assert outcome.action == "error"


def test_check_one_service_apply_returns_error_when_systemctl_fails():
    # Arrange
    job = _job_service()

    def failing_sysctl(args, **_):
        return _completed(rc=5, stderr="unit failed")

    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=_ok_pip,
        systemctl_runner=failing_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert
    assert outcome.action == "error"


# --------------------------------------------------------------------- #
# Editable-path pure helpers                                           #
# --------------------------------------------------------------------- #


def test_editable_source_dir_returns_path_when_editable():
    # Arrange
    text = '{"url": "file:///home/op/proj/scitex-todo", "dir_info": {"editable": true}}'
    # Act
    srcdir = df._editable_source_dir(text)
    # Assert
    assert srcdir == "/home/op/proj/scitex-todo"


def test_editable_source_dir_returns_none_when_not_editable():
    # Arrange
    text = (
        '{"url": "file:///home/op/proj/scitex-todo", "dir_info": {"editable": false}}'
    )
    # Act
    srcdir = df._editable_source_dir(text)
    # Assert
    assert srcdir is None


def test_editable_source_dir_returns_none_for_absent_direct_url():
    # Arrange
    # Act
    srcdir = df._editable_source_dir(None)
    # Assert
    assert srcdir is None


def test_parse_iso_to_utc_parses_offset_timestamp():
    # Arrange
    # Act
    dt = df._parse_iso_to_utc("2026-06-25T00:36:43+09:00")
    # Assert — 00:36 JST == 15:36 UTC the previous day
    assert dt.hour == 15


def test_parse_iso_to_utc_returns_none_for_empty():
    # Arrange
    # Act
    dt = df._parse_iso_to_utc("")
    # Assert
    assert dt is None


def test_parse_systemd_timestamp_returns_aware_datetime():
    # Arrange
    # Act
    dt = df._parse_systemd_timestamp_to_utc("Wed 2026-06-25 00:36:43 UTC")
    # Assert
    assert dt.tzinfo is not None


def test_parse_systemd_timestamp_returns_none_for_na():
    # Arrange
    # Act
    dt = df._parse_systemd_timestamp_to_utc("n/a")
    # Assert
    assert dt is None


def test_source_commit_time_prefers_git_over_mtime():
    # Arrange — git ISO vs an mtime of epoch 0 (1970); git must win
    git = _git_returning("2026-06-25T00:00:00+00:00")
    expected = df._parse_iso_to_utc("2026-06-25T00:00:00+00:00")
    # Act
    dt = df._source_commit_time("/src", git_runner=git, source_mtime=lambda _s: 0.0)
    # Assert
    assert dt == expected


def test_source_commit_time_falls_back_to_mtime_when_not_git():
    # Arrange — not a git work tree → use the source mtime
    git = _git_not_a_repo()
    mtime = 1_700_000_000.0
    expected = datetime.fromtimestamp(mtime, tz=timezone.utc)
    # Act
    dt = df._source_commit_time("/src", git_runner=git, source_mtime=lambda _s: mtime)
    # Assert
    assert dt == expected


# --------------------------------------------------------------------- #
# check_one_service — editable path                                    #
# --------------------------------------------------------------------- #


def test_check_one_service_editable_newer_source_detects_drift():
    # Arrange — source committed a full day AFTER the unit last started
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.drift is True


def test_check_one_service_editable_drift_uses_editable_mode():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.mode == "editable"


def test_check_one_service_editable_dry_run_returns_would_update():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.action == "would-update"


def test_check_one_service_editable_apply_restarts_unit():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert sysctl.restart_calls == [["restart", "scitex-todo.dashboard.service"]]


def test_check_one_service_editable_apply_does_not_call_pip():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    pip_calls = []

    def pip(args):
        pip_calls.append(args)
        return _completed(rc=0)

    # Act
    df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
        pip_runner=pip,
    )
    # Assert — editable repair is restart-only; pip is never invoked
    assert pip_calls == []


def test_check_one_service_editable_apply_returns_updated():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.action == "updated"


def test_check_one_service_editable_older_source_no_drift():
    # Arrange — source committed a full day BEFORE the unit last started
    job = _job_service()
    sysctl = _systemctl_active_at("Wed 2026-06-25 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-24T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.drift is False


def test_check_one_service_editable_older_source_action_ok():
    # Arrange
    job = _job_service()
    sysctl = _systemctl_active_at("Wed 2026-06-25 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-24T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.action == "ok"


def test_check_one_service_editable_older_source_apply_skips_restart():
    # Arrange — no drift, so even with --apply the unit must NOT restart
    job = _job_service()
    sysctl = _systemctl_active_at("Wed 2026-06-25 00:00:00 UTC")
    # Act
    df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-24T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert sysctl.restart_calls == []


def test_check_one_service_editable_git_failure_is_isolated():
    # Arrange — git returns nothing AND no source mtime → skip, not crash
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_not_a_repo(),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.action == "skipped"


def test_check_one_service_editable_systemctl_show_failure_is_isolated():
    # Arrange — `systemctl show` errors → cannot read unit-start → skip
    job = _job_service()

    def failing_sysctl(args, **_):
        return _completed(rc=1, stderr="Failed to get unit")

    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=failing_sysctl,
    )
    # Assert
    assert outcome.action == "skipped"


def test_check_one_service_editable_restart_failure_returns_error():
    # Arrange — drift detected, but the repair restart itself fails
    job = _job_service()

    def sysctl(args, **_):
        if args[:1] == ["show"]:
            return _completed(
                rc=0, stdout="ActiveEnterTimestamp=Tue 2026-06-24 00:00:00 UTC\n"
            )
        return _completed(rc=5, stderr="job failed")

    # Act
    outcome = df.check_one_service(
        job=job,
        apply=True,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_returning("2026-06-25T00:00:00+00:00"),
        source_mtime=_no_source_mtime(),
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.action == "error"


def test_check_one_service_editable_falls_back_to_source_mtime():
    # Arrange — not a git repo; mtime newer than unit-start → drift
    job = _job_service()
    sysctl = _systemctl_active_at("Tue 2026-06-24 00:00:00 UTC")
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_editable_direct_url(),
        git_runner=_git_not_a_repo(),
        source_mtime=lambda _s: 4_102_444_800.0,  # 2100-01-01 — far future
        systemctl_runner=sysctl,
    )
    # Assert
    assert outcome.drift is True


# --------------------------------------------------------------------- #
# check_one_service — non-editable back-compat                         #
# --------------------------------------------------------------------- #


def test_check_one_service_wheel_unchanged_uses_wheel_mode():
    # Arrange — explicit wheel (no direct_url.json) keeps PyPI behaviour
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.mode == "wheel"


def test_check_one_service_wheel_unchanged_still_detects_version_drift():
    # Arrange
    job = _job_service()
    # Act
    outcome = df.check_one_service(
        job=job,
        apply=False,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
    )
    # Assert
    assert outcome.action == "would-update"


# --------------------------------------------------------------------- #
# run_once                                                              #
# --------------------------------------------------------------------- #


def _empty_log(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "cron-deploy-freshness.log"


def test_run_once_empty_jobs_provider_records_zero_checked(tmp_path):
    # Arrange
    # Act
    result = df.run_once(
        apply=False,
        jobs_provider=lambda: [],
        log_path=_empty_log(tmp_path),
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.services_checked == 0


def test_run_once_writes_summary_line_to_log(tmp_path):
    # Arrange
    log = _empty_log(tmp_path)
    # Act
    df.run_once(
        apply=False,
        jobs_provider=lambda: [],
        log_path=log,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "SUMMARY" in log.read_text(encoding="utf-8")


def test_run_once_drift_in_one_service_increments_drift_count(tmp_path):
    # Arrange
    jobs = [_job_service()]
    # Act
    result = df.run_once(
        apply=False,
        jobs_provider=lambda: jobs,
        http_runner=_http_returning_version("0.5.3"),
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        log_path=_empty_log(tmp_path),
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.drift_count == 1


def test_run_once_apply_updates_increment_updated_count(tmp_path):
    # Arrange
    jobs = [_job_service()]
    # Act
    result = df.run_once(
        apply=True,
        jobs_provider=lambda: jobs,
        http_runner=_http_returning_version("0.5.3"),
        pip_runner=_ok_pip,
        systemctl_runner=_ok_sysctl,
        metadata_lookup=_metadata_lookup_returning(
            "scitex-todo", "scitex-todo", "0.5.2"
        ),
        direct_url_lookup=_wheel_direct_url(),
        which=lambda n: "/fake/pip" if n == "pip" else None,
        log_path=_empty_log(tmp_path),
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.updated_count == 1


def test_run_once_jobs_provider_exception_sets_error_field(tmp_path):
    # Arrange
    def bad_provider():
        raise RuntimeError("boom")

    # Act
    result = df.run_once(
        apply=False,
        jobs_provider=bad_provider,
        log_path=_empty_log(tmp_path),
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.error is not None


# --------------------------------------------------------------------- #
# Provider — pin the entry-point shape                                  #
# --------------------------------------------------------------------- #


def test_provider_returns_at_least_one_jobspec():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    jobs = _provider.provide_jobs()
    # Assert
    assert len(jobs) >= 1


def test_provider_includes_deploy_freshness():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    names = {j.name for j in _provider.provide_jobs()}
    # Assert
    assert "scitex-dev-deploy-freshness" in names


def test_provider_deploy_freshness_is_cron_kind():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "scitex-dev-deploy-freshness")
    # Assert
    assert job.kind == "cron"


def test_provider_deploy_freshness_invokes_ecosystem_cron_exec():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "scitex-dev-deploy-freshness")
    # Assert — federated cron jobs invoke `ecosystem cron exec`, NOT
    # the legacy per-package `scitex-dev cron exec`.
    assert "ecosystem cron exec scitex-dev-deploy-freshness" in job.command


def test_provider_deploy_freshness_passes_apply_in_production_line():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "scitex-dev-deploy-freshness")
    # Assert — `--apply` is in the materialized line so the cron actually
    # repairs drift; dry-run is the operator's manual interactive mode.
    assert "--apply" in job.command


# EOF
