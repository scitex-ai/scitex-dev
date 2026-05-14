#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for sync module — exercise the real production wiring against a
real `ssh` shim script on `$PATH`. No injected subprocess runners, no
canned `CompletedProcess` stand-ins.

The shim writes its argv to a log file and decides what to echo based
on `$SCITEX_SHIM_MODE` (set by each test). The ahead-check call and the
sync call are distinguished by inspecting the trailing remote command
arg the shim receives.
"""

from __future__ import annotations

import os
import stat

import pytest

from scitex_dev._core.config import DevConfig, HostConfig, PackageConfig
from scitex_dev._sync._local import (
    _check_ahead_state,
    _sync_one_package,
    sync_all,
    sync_host,
)


# ── ssh shim plumbing ────────────────────────────────────────────────────────


_SHIM_SCRIPT = """#!/usr/bin/env bash
# Real-shim ssh stand-in. Logs every invocation so the test can assert on
# the argv we built, then dispatches based on $SCITEX_SHIM_MODE and on
# whether the trailing remote command is an ahead-check or a sync.
log="$SCITEX_SHIM_LOG"
mode="${SCITEX_SHIM_MODE:-clean}"

# Append a single record per invocation. argv is space-joined; the
# trailing remote_cmd may contain spaces but is the last positional arg.
printf '%s\\n' "ARGV:$*" >> "$log"
remote_cmd="${@: -1}"
printf '%s\\n' "REMOTE:$remote_cmd" >> "$log"

# Ahead-check uses the SACDEV_STATE / SACDEV_MISSING marker pattern.
is_ahead_check() {
  echo "$remote_cmd" | grep -q "SACDEV_STATE"
}

if is_ahead_check; then
  case "$mode" in
    clean)     echo "SACDEV_STATE la=0 ra=0"; exit 0 ;;
    ahead)     echo "SACDEV_STATE la=3 ra=0"; exit 0 ;;
    diverged)  echo "SACDEV_STATE la=2 ra=5"; exit 0 ;;
    behind)    echo "SACDEV_STATE la=0 ra=5"; exit 0 ;;
    missing)   echo "SACDEV_MISSING"; exit 0 ;;
    ssh_error) echo "Connection refused" >&2; exit 255 ;;
    *)         echo "SACDEV_STATE la=0 ra=0"; exit 0 ;;
  esac
fi

# Sync call: just echo "ok" for the success path. Tests that want a
# failure path should set SCITEX_SHIM_SYNC_FAIL=1.
if [ "${SCITEX_SHIM_SYNC_FAIL:-0}" = "1" ]; then
  echo "" ; echo "remote git pull failed" >&2 ; exit 1
fi
echo "ok"
exit 0
"""


@pytest.fixture
def ssh_shim(tmp_path):
    """Install an `ssh` shim on $PATH and a log file in `tmp_path`.

    Yields a small helper:
      shim.set_mode("clean"|"ahead"|"diverged"|"behind"|"missing"|"ssh_error")
      shim.set_sync_fail(True|False)
      shim.read_log() -> list[str]  (one entry per invocation, each entry
                                      a 2-line "ARGV:...\\nREMOTE:..." block)
      shim.argvs() -> list[str]     (ARGV: lines only)
      shim.remotes() -> list[str]   (REMOTE: lines only)
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(_SHIM_SCRIPT)
    ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "ssh.log"
    log.write_text("")

    # We *don't* use pytest's monkeypatch — the fixture name is just a
    # parametrised local helper that yields and restores env vars itself.
    saved = {
        "PATH": os.environ.get("PATH"),
        "SCITEX_SHIM_LOG": os.environ.get("SCITEX_SHIM_LOG"),
        "SCITEX_SHIM_MODE": os.environ.get("SCITEX_SHIM_MODE"),
        "SCITEX_SHIM_SYNC_FAIL": os.environ.get("SCITEX_SHIM_SYNC_FAIL"),
    }
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{saved['PATH'] or ''}"
    os.environ["SCITEX_SHIM_LOG"] = str(log)
    os.environ["SCITEX_SHIM_MODE"] = "clean"
    os.environ.pop("SCITEX_SHIM_SYNC_FAIL", None)

    class _Shim:
        def set_mode(self, mode: str) -> None:
            os.environ["SCITEX_SHIM_MODE"] = mode

        def set_sync_fail(self, fail: bool) -> None:
            if fail:
                os.environ["SCITEX_SHIM_SYNC_FAIL"] = "1"
            else:
                os.environ.pop("SCITEX_SHIM_SYNC_FAIL", None)

        def read_log(self) -> list[str]:
            return log.read_text().splitlines()

        def argvs(self) -> list[str]:
            return [
                line[len("ARGV:") :]
                for line in self.read_log()
                if line.startswith("ARGV:")
            ]

        def remotes(self) -> list[str]:
            return [
                line[len("REMOTE:") :]
                for line in self.read_log()
                if line.startswith("REMOTE:")
            ]

    try:
        yield _Shim()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.pop("SCITEX_SHIM_SYNC_FAIL", None)


@pytest.fixture
def fake_host() -> HostConfig:
    return HostConfig(
        name="test",
        hostname="test.example.com",
        user="ywatanabe",
        role="dev",
        enabled=True,
        python_bin="~/.venv/bin/python",
        pip_bin="~/.venv/bin/pip",
        remote_base="~/proj",
        packages=["scitex-db"],
    )


# ── _check_ahead_state ───────────────────────────────────────────────────────


class TestCheckAheadState:
    def test_clean_repo_returns_clean_result_status_clean(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "clean"
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()


    def test_clean_repo_returns_clean_result_local_ahead_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["local_ahead"] == 0
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()


    def test_clean_repo_returns_clean_result_remote_ahead_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["remote_ahead"] == 0
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()


    def test_clean_repo_returns_clean_len_argv_1(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()
        assert len(argv) == 1


    def test_clean_repo_returns_clean_test_example_com_in_argv_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()
        assert "test.example.com" in argv[0]


    def test_clean_repo_returns_clean_batchmode_yes_in_argv_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _check_ahead_state(fake_host, "scitex-db")
        # Verify we actually built and ran the real ssh argv (sanity).
        argv = ssh_shim.argvs()
        assert "BatchMode=yes" in argv[0]

    def test_ahead_remote_with_unpushed_commits_result_status_ahead(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "ahead"


    def test_ahead_remote_with_unpushed_commits_result_local_ahead_3(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["local_ahead"] == 3

    def test_diverged_both_ahead_and_behind_result_status_diverged(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "diverged"


    def test_diverged_both_ahead_and_behind_result_local_ahead_2(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["local_ahead"] == 2


    def test_diverged_both_ahead_and_behind_result_remote_ahead_5(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["remote_ahead"] == 5

    def test_behind_only_is_clean(self, fake_host, ssh_shim):
        """Pulling 5 commits ahead on upstream is fine — no data loss risk."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("behind")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "clean"

    def test_missing_repo_reports_missing(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("missing")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "missing"

    def test_ssh_error_surfaces_result_status_error(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ssh_error")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "error"


    def test_ssh_error_surfaces_connection_refused_in_result_error(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ssh_error")
        result = _check_ahead_state(fake_host, "scitex-db")
        assert "Connection refused" in result["error"]

    def test_remote_cmd_carries_correct_dir_len_remotes_1(self, fake_host, ssh_shim):
        """The remote command must `cd` to the right per-package dir under
        host.remote_base."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        _check_ahead_state(fake_host, "scitex-db")
        remotes = ssh_shim.remotes()
        assert len(remotes) == 1
        # Production builds `cd ~/proj/scitex-db || …`.


    def test_remote_cmd_carries_correct_dir_proj_scitex_db_in_remotes_0(self, fake_host, ssh_shim):
        """The remote command must `cd` to the right per-package dir under
        host.remote_base."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        _check_ahead_state(fake_host, "scitex-db")
        remotes = ssh_shim.remotes()
        # Production builds `cd ~/proj/scitex-db || …`.
        assert "~/proj/scitex-db" in remotes[0]


    def test_remote_cmd_carries_correct_dir_sacdev_state_in_remotes_0(self, fake_host, ssh_shim):
        """The remote command must `cd` to the right per-package dir under
        host.remote_base."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        _check_ahead_state(fake_host, "scitex-db")
        remotes = ssh_shim.remotes()
        # Production builds `cd ~/proj/scitex-db || …`.
        assert "SACDEV_STATE" in remotes[0]


# ── _sync_one_package with safe mode (real ahead-check + real sync) ──────────


class TestSyncOnePackageSafeMode:
    def test_skips_when_remote_ahead_result_status_skipped_ahead(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "skipped_ahead"
        # Exactly one ssh invocation: the ahead-check. The sync step
        # must NOT have fired.
        remotes = ssh_shim.remotes()


    def test_skips_when_remote_ahead_result_local_ahead_3(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["local_ahead"] == 3
        # Exactly one ssh invocation: the ahead-check. The sync step
        # must NOT have fired.
        remotes = ssh_shim.remotes()


    def test_skips_when_remote_ahead_len_remotes_1(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        # Exactly one ssh invocation: the ahead-check. The sync step
        # must NOT have fired.
        remotes = ssh_shim.remotes()
        assert len(remotes) == 1


    def test_skips_when_remote_ahead_sacdev_state_in_remotes_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        # Exactly one ssh invocation: the ahead-check. The sync step
        # must NOT have fired.
        remotes = ssh_shim.remotes()
        assert "SACDEV_STATE" in remotes[0]


    def test_skips_when_remote_ahead_git_pull_not_in_remotes_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        # Exactly one ssh invocation: the ahead-check. The sync step
        # must NOT have fired.
        remotes = ssh_shim.remotes()
        assert "git pull" not in remotes[0]

    def test_skips_when_diverged_result_status_skipped_diverged(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "skipped_diverged"
        # No sync attempted.


    def test_skips_when_diverged_result_local_ahead_2(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["local_ahead"] == 2
        # No sync attempted.


    def test_skips_when_diverged_result_remote_ahead_5(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["remote_ahead"] == 5
        # No sync attempted.


    def test_skips_when_diverged_not_any_git_pull_in_r_for_r_in_ssh_shim(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("diverged")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        # No sync attempted.
        assert not any("git pull" in r for r in ssh_shim.remotes())

    def test_proceeds_when_clean_result_status_ok(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "ok"
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.


    def test_proceeds_when_clean_len_remotes_2(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.
        assert len(remotes) == 2


    def test_proceeds_when_clean_sacdev_state_in_remotes_0(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.
        assert "SACDEV_STATE" in remotes[0]


    def test_proceeds_when_clean_git_pull_in_remotes_1(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.
        assert "git pull" in remotes[1]


    def test_proceeds_when_clean_git_stash_in_remotes_1(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.
        assert "git stash" in remotes[1]


    def test_proceeds_when_clean_pip_install_in_remotes_1(self, fake_host, ssh_shim):
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        remotes = ssh_shim.remotes()
        # Two invocations: ahead-check then sync.
        assert "pip install" in remotes[1]

    def test_proceeds_reports_sync_failure_result_status_error(self, fake_host, ssh_shim):
        """Real sync failure surfaces as status=error with stderr message."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        ssh_shim.set_sync_fail(True)
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "error"


    def test_proceeds_reports_sync_failure_remote_git_pull_failed_in_result_error(self, fake_host, ssh_shim):
        """Real sync failure surfaces as status=error with stderr message."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("clean")
        ssh_shim.set_sync_fail(True)
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert "remote git pull failed" in result["error"]

    def test_safe_false_bypasses_check_result_status_ok(self, fake_host, ssh_shim):
        """safe=False should jump straight to the sync without any
        ahead-check, even if the shim would have flagged it ahead."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(
            fake_host, "scitex-db", stash=True, install=True, safe=False
        )
        assert result["status"] == "ok"
        remotes = ssh_shim.remotes()
        # The single call must be the sync, not an ahead-check.


    def test_safe_false_bypasses_check_len_remotes_1(self, fake_host, ssh_shim):
        """safe=False should jump straight to the sync without any
        ahead-check, even if the shim would have flagged it ahead."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(
            fake_host, "scitex-db", stash=True, install=True, safe=False
        )
        remotes = ssh_shim.remotes()
        assert len(remotes) == 1
        # The single call must be the sync, not an ahead-check.


    def test_safe_false_bypasses_check_sacdev_state_not_in_remotes_0(self, fake_host, ssh_shim):
        """safe=False should jump straight to the sync without any
        ahead-check, even if the shim would have flagged it ahead."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(
            fake_host, "scitex-db", stash=True, install=True, safe=False
        )
        remotes = ssh_shim.remotes()
        # The single call must be the sync, not an ahead-check.
        assert "SACDEV_STATE" not in remotes[0]


    def test_safe_false_bypasses_check_git_pull_in_remotes_0(self, fake_host, ssh_shim):
        """safe=False should jump straight to the sync without any
        ahead-check, even if the shim would have flagged it ahead."""
        # Arrange
        # Act
        # Assert
        ssh_shim.set_mode("ahead")
        result = _sync_one_package(
            fake_host, "scitex-db", stash=True, install=True, safe=False
        )
        remotes = ssh_shim.remotes()
        # The single call must be the sync, not an ahead-check.
        assert "git pull" in remotes[0]


# ── sync_host dry-run shape (no ssh — pure command preview) ─────────────────


class TestSyncHostDryRun:
    def test_dry_run_returns_commands_with_safe_flag_scitex_db_in_result(self, fake_host, tmp_path):
        """Dry-run must NOT touch ssh at all and must surface the
        safe-check flag plus the commands that WOULD run."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=True, config=cfg)
        assert "scitex-db" in result
        # Commands should include git pull and pip install.
        cmds = result["scitex-db"]["commands"]


    def test_dry_run_returns_commands_with_safe_flag_result_scitex_db_status_dry_run(self, fake_host, tmp_path):
        """Dry-run must NOT touch ssh at all and must surface the
        safe-check flag plus the commands that WOULD run."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=True, config=cfg)
        assert result["scitex-db"]["status"] == "dry_run"
        # Commands should include git pull and pip install.
        cmds = result["scitex-db"]["commands"]


    def test_dry_run_returns_commands_with_safe_flag_result_scitex_db_safe_check_is_true(self, fake_host, tmp_path):
        """Dry-run must NOT touch ssh at all and must surface the
        safe-check flag plus the commands that WOULD run."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=True, config=cfg)
        assert result["scitex-db"]["safe_check"] is True
        # Commands should include git pull and pip install.
        cmds = result["scitex-db"]["commands"]


    def test_dry_run_returns_commands_with_safe_flag_any_git_pull_in_c_for_c_in_cmds(self, fake_host, tmp_path):
        """Dry-run must NOT touch ssh at all and must surface the
        safe-check flag plus the commands that WOULD run."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=True, config=cfg)
        # Commands should include git pull and pip install.
        cmds = result["scitex-db"]["commands"]
        assert any("git pull" in c for c in cmds)


    def test_dry_run_returns_commands_with_safe_flag_any_pip_install_in_c_for_c_in_cmds(self, fake_host, tmp_path):
        """Dry-run must NOT touch ssh at all and must surface the
        safe-check flag plus the commands that WOULD run."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=True, config=cfg)
        # Commands should include git pull and pip install.
        cmds = result["scitex-db"]["commands"]
        assert any("pip install" in c for c in cmds)

    def test_dry_run_safe_false_carries_through(self, fake_host, tmp_path):
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_host(fake_host, confirm=False, safe=False, config=cfg)
        assert result["scitex-db"]["safe_check"] is False


# ── sync_all dry-run propagation (real call, observed via dry-run output) ───


class TestSyncAllPropagation:
    def test_safe_parameter_carries_to_dry_run_output_fake_host_name_in_result(self, fake_host, tmp_path):
        """sync_all(safe=False, confirm=False) must produce a dry-run
        result whose per-host per-package entries show safe_check=False.
        Real dispatch, real config — no fake sync_host."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_all(safe=False, confirm=False, config=cfg)
        assert fake_host.name in result
        per_pkg = result[fake_host.name]


    def test_safe_parameter_carries_to_dry_run_output_scitex_db_in_per_pkg(self, fake_host, tmp_path):
        """sync_all(safe=False, confirm=False) must produce a dry-run
        result whose per-host per-package entries show safe_check=False.
        Real dispatch, real config — no fake sync_host."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_all(safe=False, confirm=False, config=cfg)
        per_pkg = result[fake_host.name]
        assert "scitex-db" in per_pkg


    def test_safe_parameter_carries_to_dry_run_output_per_pkg_scitex_db_status_dry_run(self, fake_host, tmp_path):
        """sync_all(safe=False, confirm=False) must produce a dry-run
        result whose per-host per-package entries show safe_check=False.
        Real dispatch, real config — no fake sync_host."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_all(safe=False, confirm=False, config=cfg)
        per_pkg = result[fake_host.name]
        assert per_pkg["scitex-db"]["status"] == "dry_run"


    def test_safe_parameter_carries_to_dry_run_output_per_pkg_scitex_db_safe_check_is_false(self, fake_host, tmp_path):
        """sync_all(safe=False, confirm=False) must produce a dry-run
        result whose per-host per-package entries show safe_check=False.
        Real dispatch, real config — no fake sync_host."""
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_all(safe=False, confirm=False, config=cfg)
        per_pkg = result[fake_host.name]
        assert per_pkg["scitex-db"]["safe_check"] is False

    def test_safe_true_default_carries_to_dry_run_output(self, fake_host, tmp_path):
        # Arrange
        # Act
        # Assert
        pkg_path = tmp_path / "scitex-db"
        pkg_path.mkdir()
        cfg = DevConfig(
            packages=[
                PackageConfig(
                    name="scitex-db",
                    local_path=str(pkg_path),
                    pypi_name="scitex-db",
                    github_repo="ywatanabe1989/scitex-db",
                )
            ],
            hosts=[fake_host],
        )
        result = sync_all(safe=True, confirm=False, config=cfg)
        assert result[fake_host.name]["scitex-db"]["safe_check"] is True


# EOF
