"""Unit tests for the ``cred-distribute`` cron body.

PA-306 / STX-NM: no ``unittest.mock``, no ``monkeypatch``. Every
external seam (``sac_runner``, ``which_runner``, ``config_path``,
``log_path``, ``now``) is a keyword argument on :func:`run_once`, and
each test passes hand-rolled callables / ``tmp_path`` paths.

PA-307 / STX-TQ002 + STX-TQ007: each test has exactly one assertion
(``assert``-statement OR ``with pytest.raises(...)`` block), and the
``# Arrange`` / ``# Act`` / ``# Assert`` markers appear on their own
lines in order.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.cron import _cred_distribute


# ---------------------------------------------------------------------------
# Real-fake helpers — PA-306 bans mock, so we hand-build a CompletedProcess
# and route every call through callable kwargs the SUT already exposes.
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


def _which_finds_sac(name: str) -> str | None:
    """Real fake for ``shutil.which`` that pretends ``sac`` is on PATH."""
    if name == "sac":
        return "/fake/sac"
    return None


def _which_no_sac(name: str) -> str | None:
    """Real fake for ``shutil.which`` that pretends ``sac`` is missing."""
    return None


def _ok_runner(args, **_):
    """Real fake for ``sac_runner`` that always returns rc=0."""
    return _completed(returncode=0, stdout="synced\n")


def _empty_log(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "cron-cred-distribute.log"


def _write_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "cred-distribute.yaml"
    cfg.write_text(body, encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# _parse_config — validates the YAML schema. Pure helper, no I/O.
# ---------------------------------------------------------------------------


def test_parse_config_empty_doc_returns_no_hosts():
    # Arrange
    doc = None
    # Act
    hosts, _account = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == []


def test_parse_config_empty_doc_defaults_account_to_auto():
    # Arrange
    doc = None
    # Act
    _hosts, account = _cred_distribute._parse_config(doc)
    # Assert
    assert account == "auto"


def test_parse_config_simple_string_host_list_returns_hosts():
    # Arrange
    doc = {"hosts": ["spartan", "lab-gpu-1"], "account": "auto"}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan", "lab-gpu-1"]


def test_parse_config_account_field_defaults_to_auto_when_missing():
    # Arrange
    doc = {"hosts": ["spartan"]}
    # Act
    _hosts, account = _cred_distribute._parse_config(doc)
    # Assert
    assert account == "auto"


def test_parse_config_account_field_passed_through_when_set():
    # Arrange
    doc = {"hosts": ["spartan"], "account": "secondary"}
    # Act
    _hosts, account = _cred_distribute._parse_config(doc)
    # Assert
    assert account == "secondary"


def test_parse_config_mapping_host_entry_picks_up_name_field():
    # Arrange
    doc = {"hosts": [{"name": "spartan"}]}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan"]


def test_parse_config_mapping_host_entry_picks_up_host_field():
    # Arrange
    doc = {"hosts": [{"host": "lab-gpu-1"}]}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["lab-gpu-1"]


def test_parse_config_mapping_host_entry_with_enabled_false_is_skipped():
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


def test_parse_config_strips_whitespace_and_drops_empty_host_names():
    # Arrange
    doc = {"hosts": ["  spartan  ", ""]}
    # Act
    hosts, _ = _cred_distribute._parse_config(doc)
    # Assert
    assert hosts == ["spartan"]


def test_parse_config_raises_when_doc_is_not_a_mapping():
    # Arrange
    doc = ["spartan", "lab-gpu-1"]
    # Act
    # Assert
    with pytest.raises(ValueError, match="YAML mapping"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_when_hosts_is_not_a_list():
    # Arrange
    doc = {"hosts": "spartan"}
    # Act
    # Assert
    with pytest.raises(ValueError, match="YAML list"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_on_unsupported_host_entry_type():
    # Arrange
    doc = {"hosts": [123]}
    # Act
    # Assert
    with pytest.raises(ValueError, match="unsupported"):
        _cred_distribute._parse_config(doc)


def test_parse_config_raises_when_account_is_not_a_string():
    # Arrange
    doc = {"hosts": ["spartan"], "account": 42}
    # Act
    # Assert
    with pytest.raises(ValueError, match="must be a string"):
        _cred_distribute._parse_config(doc)


# ---------------------------------------------------------------------------
# _build_sac_args — central CLI-shape choke point.
# ---------------------------------------------------------------------------


def test_build_sac_args_freezes_canonical_argv_shape():
    # Arrange
    expected = [
        "accounts",
        "distribute",
        "--to-host",
        "spartan",
        "--account",
        "auto",
    ]
    # Act
    args = _cred_distribute._build_sac_args("spartan", "auto")
    # Assert — one place to swap if proj-scitex-agent-container changes
    # verb / flag names.
    assert args == expected


# ---------------------------------------------------------------------------
# _looks_like_subcommand_missing — keeps the cron green during the
# proj-scitex-agent-container rollout window.
# ---------------------------------------------------------------------------


def test_looks_like_subcommand_missing_recognises_click_error():
    # Arrange
    text = "Error: No such command 'distribute'."
    # Act
    matched = _cred_distribute._looks_like_subcommand_missing(text)
    # Assert
    assert matched is True


def test_looks_like_subcommand_missing_recognises_unknown_command():
    # Arrange
    text = "Unknown command: accounts"
    # Act
    matched = _cred_distribute._looks_like_subcommand_missing(text)
    # Assert
    assert matched is True


def test_looks_like_subcommand_missing_false_on_real_transport_error():
    # Arrange — actual ssh failure must be reported as a real failure so
    # a chronic auth break pages the operator via the all-attempted-failed
    # exit-1 path; it must NOT be silently downgraded to a skip.
    text = "ssh: connect to host spartan port 22: Connection refused"
    # Act
    matched = _cred_distribute._looks_like_subcommand_missing(text)
    # Assert
    assert matched is False


# ---------------------------------------------------------------------------
# run_once — config bootstrap path
# ---------------------------------------------------------------------------


def test_run_once_bootstraps_missing_config_to_existing_file(tmp_path):
    # Arrange
    cfg = tmp_path / "cred-distribute.yaml"
    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert cfg.exists()


def test_run_once_bootstrap_template_contains_documentation_header(tmp_path):
    # Arrange
    cfg = tmp_path / "cred-distribute.yaml"
    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "scitex-dev cron: cred-distribute" in cfg.read_text(encoding="utf-8")


def test_run_once_bootstrap_template_has_empty_hosts_list(tmp_path):
    # Arrange
    cfg = tmp_path / "cred-distribute.yaml"
    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "hosts: []" in cfg.read_text(encoding="utf-8")


def test_run_once_bootstrap_returns_no_outcomes(tmp_path):
    # Arrange
    cfg = tmp_path / "cred-distribute.yaml"
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.outcomes == ()


# ---------------------------------------------------------------------------
# run_once — empty hosts (no-op)
# ---------------------------------------------------------------------------


def test_run_once_empty_hosts_records_no_outcomes(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts: []\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.outcomes == ()


def test_run_once_empty_hosts_writes_audit_line_to_log(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts: []\naccount: auto\n")
    log = _empty_log(tmp_path)
    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "no hosts configured" in log.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run_once — happy path (per-host shell-out, audit logging)
# ---------------------------------------------------------------------------


def test_run_once_happy_path_invokes_sac_once_per_host(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    calls: list[list[str]] = []

    def _recording_runner(args, **_):
        calls.append(list(args))
        return _completed(returncode=0, stdout="synced\n")

    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_recording_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert len(calls) == 2


def test_run_once_happy_path_passes_canonical_argv_for_first_host(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    calls: list[list[str]] = []

    def _recording_runner(args, **_):
        calls.append(list(args))
        return _completed(returncode=0)

    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_recording_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert calls[0] == [
        "accounts",
        "distribute",
        "--to-host",
        "spartan",
        "--account",
        "auto",
    ]


def test_run_once_happy_path_reports_attempted_count(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.attempted == 2


def test_run_once_happy_path_reports_succeeded_count(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.succeeded == 2


def test_run_once_happy_path_writes_ok_marker_per_host_to_log(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    log = _empty_log(tmp_path)
    # Act
    _cred_distribute.run_once(
        config_path=cfg,
        log_path=log,
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "host=spartan account=auto ok" in log.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run_once — mixed and total failure
# ---------------------------------------------------------------------------


def _split_runner(args, **_):
    """Real fake — spartan fails (ssh refused), others succeed."""
    host = args[args.index("--to-host") + 1]
    if host == "spartan":
        return _completed(
            returncode=1,
            stderr="ssh: connect to host spartan port 22: Connection refused",
        )
    return _completed(returncode=0, stdout="synced\n")


def test_run_once_per_host_failure_keeps_succeeded_count_positive(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_split_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.succeeded == 1


def test_run_once_per_host_failure_records_failed_count(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_split_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.failed == 1


def test_run_once_per_host_failure_keeps_all_attempted_failed_false(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_split_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.all_attempted_failed is False


def _all_fail_runner(args, **_):
    return _completed(returncode=1, stderr="permission denied")


def test_run_once_all_hosts_failed_sets_all_attempted_failed_true(tmp_path):
    # Arrange
    cfg = _write_config(
        tmp_path,
        "hosts:\n  - spartan\n  - lab-gpu-1\naccount: auto\n",
    )
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_all_fail_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert — systemic outage signal; dispatcher should exit 1.
    assert result.all_attempted_failed is True


# ---------------------------------------------------------------------------
# run_once — sac subcommand missing (rollout-window grace)
# ---------------------------------------------------------------------------


def _missing_subcommand_runner(args, **_):
    return _completed(
        returncode=2,
        stderr="Error: No such command 'distribute'.\n",
    )


def test_run_once_sac_subcommand_missing_records_skipped_not_failed(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_missing_subcommand_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.skipped == 1


def test_run_once_sac_subcommand_missing_keeps_attempted_zero(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_missing_subcommand_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.attempted == 0


def test_run_once_sac_subcommand_missing_does_not_signal_all_attempted_failed(
    tmp_path,
):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_missing_subcommand_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert — rollout-window state must NOT page the operator.
    assert result.all_attempted_failed is False


# ---------------------------------------------------------------------------
# run_once — sac binary entirely absent (which_runner says None)
# ---------------------------------------------------------------------------


def _never_called_runner(args, **_):  # pragma: no cover — must not be called
    raise AssertionError("sac_runner must not be invoked when sac is absent")


def test_run_once_sac_binary_missing_records_skipped_per_host(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_never_called_runner,
        which_runner=_which_no_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.skipped == 1


def test_run_once_sac_binary_missing_records_hosts_configured(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_never_called_runner,
        which_runner=_which_no_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.hosts_configured == 1


def test_run_once_sac_binary_missing_does_not_attempt_any_host(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_never_called_runner,
        which_runner=_which_no_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert — rollout window: exit 0 expected, no `attempted` counted.
    assert result.attempted == 0


# ---------------------------------------------------------------------------
# run_once — config malformed paths
# ---------------------------------------------------------------------------


def test_run_once_malformed_yaml_sets_error_field(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts: [not, valid, yaml: missing-close\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.error is not None


def test_run_once_schema_violation_sets_error_field(tmp_path):
    # Arrange — `hosts:` is the wrong shape (string instead of list).
    cfg = _write_config(tmp_path, "hosts: spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_ok_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert "schema error" in (result.error or "")


# ---------------------------------------------------------------------------
# run_once — runner-raised exceptions packed into outcomes (cron must not crash)
# ---------------------------------------------------------------------------


def _filenotfound_runner(args, **_):
    raise FileNotFoundError("[Errno 2] No such file or directory: 'sac'")


def test_run_once_runner_filenotfound_is_packed_as_skipped(tmp_path):
    # Arrange — sac disappears between which() and subprocess.run().
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_filenotfound_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.skipped == 1


def _timeout_runner(args, **_):
    raise subprocess.TimeoutExpired(cmd=args, timeout=60.0)


def test_run_once_runner_timeout_counts_as_real_failure(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_timeout_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert — timeout is NOT a rollout-window skip; it's a real failure.
    assert result.failed == 1


def test_run_once_runner_timeout_records_timeout_message_in_outcome(tmp_path):
    # Arrange
    cfg = _write_config(tmp_path, "hosts:\n  - spartan\naccount: auto\n")
    # Act
    result = _cred_distribute.run_once(
        config_path=cfg,
        log_path=_empty_log(tmp_path),
        sac_runner=_timeout_runner,
        which_runner=_which_finds_sac,
        now=lambda: 1_000_000.0,
    )
    # Assert
    assert result.outcomes[0].stderr.startswith("sac call timed out")


# EOF
