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
from pathlib import Path

from scitex_dev._ecosystem_jobs import _deploy_freshness as df
from scitex_dev.jobs import JobSpec


# --------------------------------------------------------------------- #
# Real-fake builders                                                    #
# --------------------------------------------------------------------- #


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


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
        which=lambda n: "/fake/pip" if n == "pip" else None,
    )
    # Assert
    assert outcome.action == "error"


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
    assert "deploy-freshness" in names


def test_provider_deploy_freshness_is_cron_kind():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "deploy-freshness")
    # Assert
    assert job.kind == "cron"


def test_provider_deploy_freshness_invokes_ecosystem_cron_exec():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "deploy-freshness")
    # Assert — federated cron jobs invoke `ecosystem cron exec`, NOT
    # the legacy per-package `scitex-dev cron exec`.
    assert "ecosystem cron exec deploy-freshness" in job.command


def test_provider_deploy_freshness_passes_apply_in_production_line():
    # Arrange
    from scitex_dev._ecosystem_jobs import _provider

    # Act
    job = next(j for j in _provider.provide_jobs() if j.name == "deploy-freshness")
    # Assert — `--apply` is in the materialized line so the cron actually
    # repairs drift; dry-run is the operator's manual interactive mode.
    assert "--apply" in job.command


# EOF
