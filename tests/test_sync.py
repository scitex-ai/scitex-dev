#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for sync module — focuses on the new ahead-check safety path.

The full SSH round-trip can't run in CI, so we mock subprocess.run and
exercise: parse paths, skip branches, and parameter propagation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scitex_dev.config import HostConfig
from scitex_dev.sync import (
    _check_ahead_state,
    _sync_one_package,
    sync_all,
    sync_host,
)


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
    @patch("scitex_dev.sync.subprocess.run")
    def test_clean_repo_returns_clean(self, mock_run, fake_host):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="SACDEV_STATE la=0 ra=0", stderr=""
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "clean"
        assert result["local_ahead"] == 0
        assert result["remote_ahead"] == 0

    @patch("scitex_dev.sync.subprocess.run")
    def test_ahead_remote_with_unpushed_commits(self, mock_run, fake_host):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="SACDEV_STATE la=3 ra=0", stderr=""
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "ahead"
        assert result["local_ahead"] == 3

    @patch("scitex_dev.sync.subprocess.run")
    def test_diverged_both_ahead_and_behind(self, mock_run, fake_host):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="SACDEV_STATE la=2 ra=5", stderr=""
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "diverged"
        assert result["local_ahead"] == 2
        assert result["remote_ahead"] == 5

    @patch("scitex_dev.sync.subprocess.run")
    def test_behind_only_is_clean(self, mock_run, fake_host):
        """Pulling 5 commits ahead on upstream is fine — no data loss risk."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="SACDEV_STATE la=0 ra=5", stderr=""
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "clean"

    @patch("scitex_dev.sync.subprocess.run")
    def test_missing_repo_reports_missing(self, mock_run, fake_host):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="SACDEV_MISSING", stderr=""
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "missing"

    @patch("scitex_dev.sync.subprocess.run")
    def test_ssh_error_surfaces(self, mock_run, fake_host):
        mock_run.return_value = MagicMock(
            returncode=255, stdout="", stderr="Connection refused"
        )
        result = _check_ahead_state(fake_host, "scitex-db")
        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


# ── _sync_one_package with safe mode ─────────────────────────────────────────


class TestSyncOnePackageSafeMode:
    @patch("scitex_dev.sync._check_ahead_state")
    @patch("scitex_dev.sync.subprocess.run")
    def test_skips_when_remote_ahead(self, mock_run, mock_check, fake_host):
        mock_check.return_value = {
            "status": "ahead",
            "local_ahead": 2,
            "remote_ahead": 0,
        }
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "skipped_ahead"
        assert result["local_ahead"] == 2
        # The actual sync command should NOT have been invoked
        mock_run.assert_not_called()

    @patch("scitex_dev.sync._check_ahead_state")
    @patch("scitex_dev.sync.subprocess.run")
    def test_skips_when_diverged(self, mock_run, mock_check, fake_host):
        mock_check.return_value = {
            "status": "diverged",
            "local_ahead": 1,
            "remote_ahead": 3,
        }
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "skipped_diverged"
        mock_run.assert_not_called()

    @patch("scitex_dev.sync._check_ahead_state")
    @patch("scitex_dev.sync.subprocess.run")
    def test_proceeds_when_clean(self, mock_run, mock_check, fake_host):
        mock_check.return_value = {
            "status": "clean",
            "local_ahead": 0,
            "remote_ahead": 0,
        }
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = _sync_one_package(fake_host, "scitex-db", stash=True, install=True)
        assert result["status"] == "ok"
        mock_run.assert_called_once()

    @patch("scitex_dev.sync._check_ahead_state")
    @patch("scitex_dev.sync.subprocess.run")
    def test_safe_false_bypasses_check(self, mock_run, mock_check, fake_host):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        _sync_one_package(fake_host, "scitex-db", stash=True, install=True, safe=False)
        mock_check.assert_not_called()


# ── sync_host dry-run shape ──────────────────────────────────────────────────


class TestSyncHostDryRun:
    @patch("scitex_dev.sync.load_config")
    def test_dry_run_returns_commands_with_safe_flag(self, mock_load, fake_host):
        mock_cfg = MagicMock()
        mock_cfg.packages = []
        mock_load.return_value = mock_cfg
        with patch(
            "scitex_dev.sync._get_host_packages",
            return_value=[("scitex-db", "scitex-db")],
        ):
            result = sync_host(fake_host, confirm=False, safe=True)
        assert "scitex-db" in result
        assert result["scitex-db"]["status"] == "dry_run"
        assert result["scitex-db"]["safe_check"] is True
        # Commands should include git pull
        assert any("git pull" in c for c in result["scitex-db"]["commands"])


# ── sync_all parameter propagation ───────────────────────────────────────────


class TestSyncAllPropagation:
    @patch("scitex_dev.sync.load_config")
    @patch("scitex_dev.sync.get_enabled_hosts")
    @patch("scitex_dev.sync.sync_host")
    def test_safe_parameter_forwarded(
        self, mock_sync_host, mock_enabled, mock_load, fake_host
    ):
        mock_enabled.return_value = [fake_host]
        mock_sync_host.return_value = {}
        sync_all(safe=False, confirm=True)
        # sync_all -> sync_host should receive safe=False
        _, kwargs = mock_sync_host.call_args
        assert kwargs["safe"] is False
        assert kwargs["confirm"] is True
