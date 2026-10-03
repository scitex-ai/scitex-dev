#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem cron``.

The ``list`` command runs against the real built-in jobs (no patching),
and ``install`` is exercised in ``--dry-run`` mode so no real crontab is
touched.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_cron_list_shows_builtin_ci_watch(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list"])
    # Assert
    assert "ci-watch" in result.output


def test_cron_install_dry_run_emits_managed_block(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "install", "--dry-run"])
    # Assert
    assert "scitex-dev-ecosystem" in result.output


def test_cron_install_without_yes_refuses(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "install"])
    # Assert
    assert result.exit_code == 2


def test_cron_install_unknown_name_errors(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "install", "--name", "no.such.job", "--dry-run"]
    )
    # Assert
    assert result.exit_code != 0


def test_cron_install_named_dry_run_filters_to_one_job(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "install", "--name", "ci-watch", "--dry-run"]
    )
    # Assert
    assert "quota-keepalive" not in result.output


def test_cron_list_json_emits_array(runner):
    # Arrange
    import json

    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list", "--json"])
    # Assert
    # `.stdout`, not `.output`: CliRunner's `.output` MIXES stderr in, and the
    # old spelling now forwards through a Phase W alias that warns on stderr.
    # Reading the mixed stream made this test depend on whether the
    # once-per-session warning had already fired — green serially, red under
    # xdist. The command's contract is data on stdout, diagnostics on stderr;
    # assert on the stream the contract names.
    assert isinstance(json.loads(result.stdout), list)


def test_cron_group_help_lists_install_verb(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "--help"])
    # Assert
    assert "install" in result.output


def test_cron_uninstall_dry_run_does_not_require_yes(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "uninstall", "--dry-run"])
    # Assert
    assert result.exit_code == 0


def test_cron_uninstall_named_dry_run_does_not_require_yes(runner):
    # Arrange
    # Act
    result = runner.invoke(
        main, ["ecosystem", "cron", "uninstall", "--name", "ci-watch", "--dry-run"]
    )
    # Assert
    assert result.exit_code == 0


def test_cron_uninstall_without_yes_refuses(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "uninstall"])
    # Assert
    assert result.exit_code == 2


def test_cron_list_shows_provider_source_label(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["ecosystem", "cron", "list", "--json"])
    # Assert
    assert "scitex-dev" in result.output


@pytest.fixture
def missing_delivery_snapshot(tmp_path):
    """Only this optional job's explicit input selector, restored at teardown."""
    import os
    from scitex_dev._ecosystem_jobs._apps_delivery import SNAPSHOT_ENV

    saved = os.environ.get(SNAPSHOT_ENV)
    os.environ[SNAPSHOT_ENV] = str(tmp_path / "absent.json")
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(SNAPSHOT_ENV, None)
        else:
            os.environ[SNAPSHOT_ENV] = saved


def test_apps_delivery_dispatch_refuses_apply_before_read():
    # Arrange
    from click import ClickException
    from scitex_dev._cli.ecosystem._cmds._jobs_cron import _dispatch_federated_job

    # Act
    with pytest.raises(ClickException) as error:
        _dispatch_federated_job("scitex-dev-apps-delivery-observe", apply=True, all_jobs=[])
    # Assert
    assert str(error.value) == "apps delivery observer is read-only; --apply is refused"


def test_apps_delivery_dispatch_propagates_missing_input(missing_delivery_snapshot, capsys):
    # Arrange
    import json
    from click import ClickException
    from scitex_dev._cli.ecosystem._cmds._jobs_cron import _dispatch_federated_job

    # Act
    with pytest.raises(ClickException) as error:
        _dispatch_federated_job("scitex-dev-apps-delivery-observe", apply=False, all_jobs=[])
    output = json.loads(capsys.readouterr().out)
    # Assert
    assert (str(error.value), output["exit_code"], output["errors"], output["findings"]) == (
        "apps delivery observation failed: snapshot_read_or_format_failure",
        2, ["snapshot_read_or_format_failure"], [],
    )


# EOF
