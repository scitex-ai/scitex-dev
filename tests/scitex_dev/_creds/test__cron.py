"""Unit tests for scitex_dev._creds._cron."""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._creds import _cron


def test_build_cron_line_default_interval_is_hourly_line_startswith_0(tmp_path):
    # Arrange
    # Act
    # Assert
    line = _cron.build_cron_line(
        60, log_path=tmp_path / "x.log", cli_path="/x/scitex-dev"
    )
    assert line.startswith("0 * * * *")


def test_build_cron_line_default_interval_is_hourly_cron_marker_in_line(tmp_path):
    # Arrange
    # Act
    # Assert
    line = _cron.build_cron_line(
        60, log_path=tmp_path / "x.log", cli_path="/x/scitex-dev"
    )
    assert _cron.MARKER in line


def test_build_cron_line_default_interval_is_hourly_x_scitex_dev_creds_rotate_all_yes_in_lin(tmp_path):
    # Arrange
    # Act
    # Assert
    line = _cron.build_cron_line(
        60, log_path=tmp_path / "x.log", cli_path="/x/scitex-dev"
    )
    assert "/x/scitex-dev creds rotate-all --yes" in line


def test_build_cron_line_15_minutes():
    # Arrange
    # Act
    # Assert
    line = _cron.build_cron_line(
        15, log_path=Path("/t/l.log"), cli_path="/x/scitex-dev"
    )
    assert line.startswith("*/15 * * * *")


def test_build_cron_line_hours():
    # Arrange
    # Act
    # Assert
    line = _cron.build_cron_line(
        180, log_path=Path("/t/l.log"), cli_path="/x/scitex-dev"
    )
    assert line.startswith("0 */3 * * *")


def test_build_cron_line_rejects_zero():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        _cron.build_cron_line(0)


class _FakeCrontab:
    """Recording fake for the crontab read/write seam."""

    def __init__(self, initial: str = ""):
        self.text = initial
        self.write_count = 0

    def read(self) -> str:
        return self.text

    def write(self, content: str) -> None:
        self.text = content
        self.write_count += 1


def test_install_idempotent_replaces_existing_line_startswith_0(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "# unrelated job\n"
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old/scitex-dev creds rotate-all --yes {_cron.MARKER}\n"
    )
    log = tmp_path / "logs" / "creds.log"

    line = _cron.install(
        60,
        log_path=log,
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )

    assert line.startswith("0 * * * *")


def test_install_idempotent_replaces_existing_crontab_text_count__cron_marker_1(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "# unrelated job\n"
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old/scitex-dev creds rotate-all --yes {_cron.MARKER}\n"
    )
    log = tmp_path / "logs" / "creds.log"

    line = _cron.install(
        60,
        log_path=log,
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )

    assert crontab.text.count(_cron.MARKER) == 1


def test_install_idempotent_replaces_existing_0_0_bin_true_in_crontab_text(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "# unrelated job\n"
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old/scitex-dev creds rotate-all --yes {_cron.MARKER}\n"
    )
    log = tmp_path / "logs" / "creds.log"

    line = _cron.install(
        60,
        log_path=log,
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )

    assert "0 0 * * * /bin/true" in crontab.text


def test_install_idempotent_replaces_existing_log_parent_is_dir(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "# unrelated job\n"
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old/scitex-dev creds rotate-all --yes {_cron.MARKER}\n"
    )
    log = tmp_path / "logs" / "creds.log"

    line = _cron.install(
        60,
        log_path=log,
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )

    assert log.parent.is_dir()  # ensures we mkdir the log dir


def test_install_dry_run_does_not_write_crontab_write_count_0(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab("")
    line = _cron.install(
        60,
        dry_run=True,
        log_path=tmp_path / "x.log",
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )
    assert crontab.write_count == 0


def test_install_dry_run_does_not_write_cron_marker_in_line(tmp_path):
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab("")
    line = _cron.install(
        60,
        dry_run=True,
        log_path=tmp_path / "x.log",
        cli_path="/x/scitex-dev",
        read_fn=crontab.read,
        write_fn=crontab.write,
    )
    assert _cron.MARKER in line


def test_uninstall_removes_only_managed_lines_removed_2():
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old {_cron.MARKER}\n"
        f"0 2 * * * /old2 {_cron.MARKER}\n"
    )
    removed = _cron.uninstall(read_fn=crontab.read, write_fn=crontab.write)
    assert removed == 2


def test_uninstall_removes_only_managed_lines_cron_marker_not_in_crontab_text():
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old {_cron.MARKER}\n"
        f"0 2 * * * /old2 {_cron.MARKER}\n"
    )
    removed = _cron.uninstall(read_fn=crontab.read, write_fn=crontab.write)
    assert _cron.MARKER not in crontab.text


def test_uninstall_removes_only_managed_lines_bin_true_in_crontab_text():
    # Arrange
    # Act
    # Assert
    crontab = _FakeCrontab(
        "0 0 * * * /bin/true\n"
        f"0 1 * * * /old {_cron.MARKER}\n"
        f"0 2 * * * /old2 {_cron.MARKER}\n"
    )
    removed = _cron.uninstall(read_fn=crontab.read, write_fn=crontab.write)
    assert "/bin/true" in crontab.text


def test_uninstall_dry_run_counts_only():
    # Arrange
    # Act
    # Assert
    def _read():
        return "no managed line\n"

    def _write(_):
        raise AssertionError("should not write in dry-run")

    assert _cron.uninstall(dry_run=True, read_fn=_read, write_fn=_write) == 0
