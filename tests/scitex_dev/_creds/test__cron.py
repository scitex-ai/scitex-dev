"""Unit tests for scitex_dev._creds._cron."""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._creds import _cron


def test_build_cron_line_default_interval_is_hourly(tmp_path):
    line = _cron.build_cron_line(
        60, log_path=tmp_path / "x.log", cli_path="/x/scitex-dev"
    )
    assert line.startswith("0 * * * *")
    assert _cron.MARKER in line
    assert "/x/scitex-dev creds rotate-all --yes" in line


def test_build_cron_line_15_minutes():
    line = _cron.build_cron_line(
        15, log_path=Path("/t/l.log"), cli_path="/x/scitex-dev"
    )
    assert line.startswith("*/15 * * * *")


def test_build_cron_line_hours():
    line = _cron.build_cron_line(
        180, log_path=Path("/t/l.log"), cli_path="/x/scitex-dev"
    )
    assert line.startswith("0 */3 * * *")


def test_build_cron_line_rejects_zero():
    with pytest.raises(ValueError):
        _cron.build_cron_line(0)


def test_install_idempotent_replaces_existing(monkeypatch, tmp_path):
    state = {
        "text": (
            "# unrelated job\n"
            "0 0 * * * /bin/true\n"
            f"0 1 * * * /old/scitex-dev creds rotate-all --yes {_cron.MARKER}\n"
        )
    }

    def fake_read():
        return state["text"]

    def fake_write(content):
        state["text"] = content

    monkeypatch.setattr(_cron, "read_crontab", fake_read)
    monkeypatch.setattr(_cron, "write_crontab", fake_write)
    log = tmp_path / "logs" / "creds.log"

    line = _cron.install(60, log_path=log, cli_path="/x/scitex-dev")

    assert line.startswith("0 * * * *")
    assert state["text"].count(_cron.MARKER) == 1
    assert "0 0 * * * /bin/true" in state["text"]
    assert log.parent.is_dir()  # ensures we mkdir the log dir


def test_install_dry_run_does_not_write(monkeypatch, tmp_path):
    called = {"n": 0}
    monkeypatch.setattr(_cron, "read_crontab", lambda: "")
    monkeypatch.setattr(
        _cron,
        "write_crontab",
        lambda _: called.__setitem__("n", called["n"] + 1),
    )
    line = _cron.install(
        60, dry_run=True, log_path=tmp_path / "x.log", cli_path="/x/scitex-dev"
    )
    assert called["n"] == 0
    assert _cron.MARKER in line


def test_uninstall_removes_only_managed_lines(monkeypatch):
    state = {
        "text": (
            "0 0 * * * /bin/true\n"
            f"0 1 * * * /old {_cron.MARKER}\n"
            f"0 2 * * * /old2 {_cron.MARKER}\n"
        )
    }
    monkeypatch.setattr(_cron, "read_crontab", lambda: state["text"])
    monkeypatch.setattr(
        _cron,
        "write_crontab",
        lambda c: state.__setitem__("text", c),
    )
    removed = _cron.uninstall()
    assert removed == 2
    assert _cron.MARKER not in state["text"]
    assert "/bin/true" in state["text"]


def test_uninstall_dry_run_counts_only():
    state = "no managed line\n"

    class _Mod:
        @staticmethod
        def read_crontab():
            return state

        @staticmethod
        def write_crontab(_):
            raise AssertionError("should not write in dry-run")

    import scitex_dev._creds._cron as real

    real_read = real.read_crontab
    real_write = real.write_crontab
    real.read_crontab = _Mod.read_crontab
    real.write_crontab = _Mod.write_crontab
    try:
        assert real.uninstall(dry_run=True) == 0
    finally:
        real.read_crontab = real_read
        real.write_crontab = real_write
