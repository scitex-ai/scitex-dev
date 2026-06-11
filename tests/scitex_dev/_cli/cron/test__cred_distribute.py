"""Unit tests for the ``cred-distribute`` cron body.

The body is exercised via real fakes (PA-306 / STX-NM*) — no
``unittest.mock``, no monkeypatching. Every external seam
(``sac_runner``, ``config_path``, ``log_path``, ``now``) is a keyword
argument on :func:`run_once`, and we pass hand-rolled callables /
``tmp_path`` paths from the tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.cron import _cred_distribute


# ---------------------------------------------------------------------------
# Fake CompletedProcess builder — PA-306 banishes mock entirely, so we hand-
# build the object the real `subprocess.run` would return. Keeps the test
# body explicit about exactly what the dispatch loop sees.
# ---------------------------------------------------------------------------


def _completed(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=args or [],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# _parse_config — validates the YAML schema. Pure helper, no I/O.
# ---------------------------------------------------------------------------


def test_parse_config_empty_doc_returns_no_hosts_default_account():
    # Arrange
    # Act
    hosts, account = _cred_distribute._parse_config(None)
    # Assert
    assert hosts == []
    assert account == "auto"


def test_parse_config_simple_string_host_list_returns_hosts():
    # Arrange
    doc = {"hosts": ["spartan", "lab-gpu-1"], "account": "auto"}
    # Act
    hosts, account = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan", "lab-gpu-1"]
    assert account == "auto"


def test_parse_config_account_field_defaults_to_auto_when_missing():
    # Arrange
    doc = {"hosts": ["spartan"]}
    # Act
    hosts, account = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan"]
    assert account == "auto"


def test_parse_config_mapping_host_entry_picks_up_name_field():
    # Arrange
    doc = {"hosts": [{"name": "spartan"}, {"host": "lab-gpu-1"}]}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan", "lab-gpu-1"]


def test_parse_config_mapping_host_entry_with_enabled_false_skipped():
    # Arrange
    doc = {
        "hosts": [
            {"name": "spartan", "enabled": True},
            {"name": "muted-host", "enabled": False},
        ]
    }
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan"]


def test_parse_config_strips_whitespace_from_host_names():
    # Arrange
    doc = {"hosts": ["  spartan  ", ""]}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert — empty string is dropped, whitespace stripped.
    assert hosts == ["spartan"]


def test_parse_config_raises_when_doc_is_not_a_mapping():
    # Arrange
    doc = ["spartan", "lab-gpu-1"]
    # Act / Assert
    with pytest.raises(ValueError, match="YAML mapping"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_when_hosts_is_not_a_list():
    # Arrange
    doc = {"hosts": "spartan"}
    # Act / Assert
    with pytest.raises(ValueError, match="YAML list"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_on_unsupported_host_entry_type():
    # Arrange
    doc = {"hosts": [123]}
    # Act / Assert
    with pytest.raises(ValueError, match="unsupported"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_when_account_is_not_a_string():
    # Arrange
    doc = {"hosts": ["spartan"], "account": 42}
    # Act / Assert
    with pytest.raises(ValueError, match="must be a string"):
        _cred_distribute._parse_config(doc)


# ---------------------------------------------------------------------------
# _build_sac_args — central CLI-shape choke point.
# ---------------------------------------------------------------------------


def test_build_sac_args_uses_to_host_and_account_flags():
    # Arrange
    # Act
    args = _cred_distribute._build_sac_args("spartan", "auto")
    # Assert — the exact shape we coordinated; one place to swap if the
    # proj-scitex-agent-container CLI changes verb / flag names.
    assert args == ["accounts", "distribute", "--to-host", "spartan", "--account", "auto"]


# ---------------------------------------------------------------------------
# _looks_like_subcommand_missing — keeps the cron green during the
# proj-scitex-agent-container rollout window.
# ---------------------------------------------------------------------------


def test_looks_like_subcommand_missing_recognises_click_error():
    # Arrange
    text = "Error: No such command 'distribute'."
    # Act / Assert
    assert _cred_distribute._looks_like_subcommand_missing(text) is True


def test_looks_like_subcommand_missing_recognises_unknown_command():
    # Arrange
    text = "Unknown command: accounts"
    # Act / Assert
    assert _cred_distribute._looks_like_subcommand_missing(text) is True


def test_looks_like_subcommand_missing_false_on_real_transport_error():
    # Arrange — an actual ssh failure is NOT a missing-subcommand and must be
    # reported as a real failure (so a chronic auth break pages the operator
    # via the all-attempted-failed exit-1 path).
    text = "ssh: connect to host spartan port 22: Connection refused"
    # Act / Assert
    assert _cred_distribute._looks_like_subcommand_missing(text) is False


# ---------------------------------------------------------------------------
# run_once — end-to-end behaviour. Exercises the bootstrap, no-op, success,
# per-host failure, sac-missing, and all-failed exit-code paths.
# ---------------------------------------------------------------------------


def _empty_log(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "cron-cred-distribute.log"


def _write_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "cred-distribute.yaml"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def test_run_once_bootstraps_missing_config_and_returns_no_hosts(tmp_path):
    # Arrange
    cfg = tmp_path / "cred-distribute.yaml"
    assert not cfg.exists()
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=lambda args, **_: _completed(),
        now=lambda: 1_000_000.0,
    )
    # Assert — file was written with the documented template, sweep was a no-op.
    assert cfg.exists()
    body = cfg.read_text(encoding="utf-8")
    assert "scitex-dev cron: cred-distribute" in body
    assert "hosts: []" in body
    assert result.error is None
    assert result.hosts_configured == 0
    assert result.outcomes == ()


def test_run_once_empty_hosts_is_a_logged_no_op(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts: []\naccount: auto\n")
    log = _empty_log(tmp_path)

    def _runner(args, **_):  # pragma: no cover — should not be called
        raise AssertionError("sac must not run when hosts: []")

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.error is None
    assert result.hosts_configured == 0
    assert result.outcomes == ()
    assert log.exists()
    assert "no hosts configured" in log.read_text(encoding="utf-8")


def test_run_once_happy_path_dispatches_per_host_and_logs(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    log = _empty_log(tmp_path)
    calls: list[list[str]] = []

    def _runner(args, **_):
        calls.append(list(args))
        return _completed(returncode=0, stdout="synced\n")

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert — both hosts called with the canonical CLI shape, both succeeded,
    # audit log has one line per host.
    assert calls == [
        ["accounts", "distribute", "--to-host", "spartan", "--account", "auto"],
        ["accounts", "distribute", "--to-host", "lab-gpu-1", "--account", "auto"],
    ]
    assert result.error is None
    assert result.hosts_configured == 2
    assert result.attempted == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.all_attempted_failed is False
    body = log.read_text(encoding="utf-8")
    assert "host=spartan account=auto ok" in body
    assert "host=lab-gpu-1 account=auto ok" in body


def test_run_once_per_host_failure_does_not_poison_remaining_hosts(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    log = _empty_log(tmp_path)

    def _runner(args, **_):
        host = args[args.index("--to-host") + 1]
        if host == "spartan":
            return _completed(
                returncode=1,
                stderr="ssh: connect to host spartan port 22: Connection refused",
            )
        return _completed(returncode=0, stdout="synced\n")

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert — one failed, one succeeded; not "all attempted failed" so the
    # dispatcher will exit 0.
    assert result.error is None
    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.all_attempted_failed is False


def test_run_once_all_hosts_failed_sets_all_attempted_failed_true(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    log = _empty_log(tmp_path)

    def _runner(args, **_):
        return _completed(returncode=1, stderr="permission denied")

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert — systemic outage signal; dispatcher should exit 1.
    assert result.error is None
    assert result.attempted == 2
    assert result.failed == 2
    assert result.all_attempted_failed is True


def test_run_once_sac_subcommand_missing_counts_as_skipped_not_failed(tmp_path):
    # Arrange — proj-scitex-agent-container hasn't shipped the verb yet,
    # so sac exits non-zero with a "no such command" stderr.
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    log = _empty_log(tmp_path)

    def _runner(args, **_):
        return _completed(
            returncode=2,
            stderr="Error: No such command 'distribute'.\n",
        )

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert — skipped path keeps the cron green during the rollout window.
    assert result.error is None
    assert result.attempted == 0
    assert result.skipped == 1
    assert result.failed == 0
    assert result.all_attempted_failed is False


def test_run_once_sac_binary_missing_returns_skipped_outcomes(tmp_path, monkeypatch):
    # Arrange — make shutil.which lie about `sac` not being on PATH. This is
    # one allowed use of monkeypatch: shutil.which has no in-process seam
    # to replace via kwarg (it reads $PATH at call time), so a pytest-level
    # override is the simplest correct substitute.
    import shutil as _shutil

    monkeypatch.setattr(
        _shutil, "which", lambda name: None if name == "sac" else "/usr/bin/" + name
    )
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    log = _empty_log(tmp_path)

    def _runner(args, **_):  # pragma: no cover — must not be called
        raise AssertionError("sac binary missing → runner must not be invoked")

    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_runner,
        now=lambda: 1_000_000.0,
    )
    # Assert — fully skipped; exit code stays 0 (capability not yet shipped).
    assert result.error is None
    assert result.hosts_configured == 1
    assert result.attempted == 0
    assert result.skipped == 1
    assert result.failed == 0


def test_run_once_malformed_yaml_sets_error_field(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts: [not, valid, yaml: missing-close\n")
    log = _empty_log(tmp_path)
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=lambda args, **_: _completed(),
        now=lambda: 1_000_000.0,
    )
    # Assert — config-level failure surfaces as `error`; the dispatcher will
    # exit non-zero so the operator sees the breakage.
    assert result.error is not None
    assert "failed to load" in result.error


def test_run_once_schema_violation_sets_error_field(tmp_path):
    # Arrange — `hosts:` is the wrong shape (string instead of list).
    cfg = _write_config(tmp_path, "hosts: spartan\naccount: auto\n")
    log = _empty_log(tmp_path)
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=lambda args, **_: _completed(),
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.error is not None
    assert "schema error" in result.error


def test_run_once_runner_raises_filenotfound_is_skipped_not_crashed(tmp_path):
    # Arrange — simulate the sac binary disappearing between `shutil.which`
    # and the subprocess call (rare but possible on a host where the
    # operator is uninstalling sac mid-tick).
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    log = _empty_log(tmp_path)

    def _runner(args, **_):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'sac'")

    # We bypass the shutil.which short-circuit by patching it to *find* sac
    # so the runner path is exercised.
    import shutil as _shutil

    real_which = _shutil.which

    def _which(name, *a, **kw):
        if name == "sac":
            return "/fake/sac"
        return real_which(name, *a, **kw)

    # Local override — restored by pytest at teardown via monkeypatch when
    # used; here we're keeping the test self-contained, so we re-assign and
    # restore manually.
    _shutil.which = _which
    try:
        result = _cred_distribute.run_once(
            config_path=cfg,
            log_path=log,
            sac_runner=_runner,
            now=lambda: 1_000_000.0,
        )
    finally:
        _shutil.which = real_which
    # Assert — packed into a HostOutcome, not raised.
    assert result.error is None
    assert result.attempted == 0
    assert result.skipped == 1


def test_run_once_runner_raises_timeout_is_recorded_as_failure(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    log = _empty_log(tmp_path)

    def _runner(args, **_):
        raise subprocess.TimeoutExpired(cmd=args, timeout=60.0)

    import shutil as _shutil

    real_which = _shutil.which
    _shutil.which = lambda name, *a, **kw: "/fake/sac" if name == "sac" else real_which(
        name, *a, **kw
    )
    try:
        result = _cred_distribute.run_once(
            config_path=cfg,
            log_path=log,
            sac_runner=_runner,
            now=lambda: 1_000_000.0,
        )
    finally:
        _shutil.which = real_which
    # Assert — timeout is a real failure, NOT a skip.
    assert result.error is None
    assert result.attempted == 1
    assert result.failed == 1
    assert result.outcomes[0].stderr.startswith("sac call timed out")


# EOF
