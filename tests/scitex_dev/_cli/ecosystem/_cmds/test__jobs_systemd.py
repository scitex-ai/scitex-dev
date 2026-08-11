#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev systemd`` — now a DEPRECATED alias over service + timer.

The group was organised by MECHANISM and fused two JobSpec kinds the
validator keeps apart. It survives only so the old spelling — which lives
in crontabs, unit files, scripts and agent prompts across the fleet, none
of them greppable from here — keeps resolving while it is retired.

Two contracts pinned here, both of them load-bearing:

1. THE EXPIRY IS DATA, NOT PROSE. A sibling auditor rule FAILS once
   ``remove_after`` passes. A sunset only a human can read is a sunset
   nobody enforces, so the three keys are asserted literally.

2. THE WARNING NEVER TOUCHES STDOUT. A deprecation notice that corrupts
   the output of the command it deprecates is worse than silence —
   measured elsewhere in this repo as a `WARN:` on stdout turning 7 tests
   red across three unrelated PRs. `systemd list --json` must still parse
   with the deprecation path fully active.

No mocks (NM001-003): a REAL entry-point provider, a REAL temp $HOME.
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli.ecosystem._cmds import _jobs_systemd as SD


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_home(tmp_path):
    prev = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path / ".config" / "systemd" / "user"
    finally:
        if prev is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prev


_ARGV = ["ecosystem", "dev", "systemd"]


# ----------------------------------------------------------------------
# Machine-readable expiry.
# ----------------------------------------------------------------------


def test_the_deprecation_records_when_it_was_deprecated():
    # Arrange — a real value, in code, for the auditor to read.
    # Act
    value = SD.DEPRECATION["deprecated"]
    # Assert
    assert value == "2026-08"


def test_the_deprecation_records_a_removal_deadline():
    # Arrange — the auditor rule FAILS once this passes. A missing or
    # decorative value would make the rule unenforceable.
    # Act
    value = SD.DEPRECATION["remove_after"]
    # Assert
    assert value == "2026-10"


def test_the_deprecation_names_both_replacements():
    # Arrange — one mechanism group split into TWO kind groups, so a
    # replacement naming only one of them would strand the other half.
    # Act
    value = SD.DEPRECATION["replacement"]
    # Assert
    assert value == "ecosystem dev service / ecosystem dev timer"


def test_the_group_object_carries_the_expiry_for_a_static_auditor(runner):
    # Arrange — the auditor reads the COMMAND object, not this module's
    # globals, so the stamp has to survive registration.
    ecosystem = main.commands["ecosystem"]
    dev = ecosystem.commands["dev"]
    # Act
    stamped = getattr(dev.commands["systemd"], "_deprecation", None)
    # Assert
    assert stamped == SD.DEPRECATION


# ----------------------------------------------------------------------
# stdout purity with the deprecation path ACTIVE.
# ----------------------------------------------------------------------


def test_the_deprecation_warning_goes_to_stderr(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    # Assert
    assert "DEPRECATED" in result.stderr


def test_json_stdout_parses_with_the_deprecation_path_active(
    runner, installed_job_provider
):
    # Arrange — THE regression this test exists for. The warning fires
    # (asserted above) and stdout is still pure JSON.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    # Assert
    assert isinstance(json.loads(result.stdout), list)


def test_the_alias_still_returns_both_kinds(runner, installed_job_provider):
    # Arrange — deprecated must still WORK, or the migration breaks every
    # un-greppable caller at once.
    # Act
    result = runner.invoke(main, _ARGV + ["list", "--json"])
    names = {row["name"] for row in json.loads(result.stdout)}
    # Assert
    assert {"testpkg.svc", "testpkg.sysjob"} <= names


def test_the_warning_names_the_replacement(runner, installed_job_provider):
    # Arrange — a deprecation that does not say what to use instead just
    # moves the lookup onto the reader.
    # Act
    result = runner.invoke(main, _ARGV + ["list"])
    # Assert
    assert "ecosystem dev service" in result.stderr


# ----------------------------------------------------------------------
# Forwarding still writes real units.
# ----------------------------------------------------------------------


def test_the_alias_install_writes_the_timer_unit(
    runner, installed_job_provider, temp_home
):
    # Arrange
    # Act
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert (temp_home / "testpkg.sysjob.timer").exists()


def test_the_alias_install_dry_run_emits_a_unit(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, _ARGV + ["install", "--dry-run"])
    # Assert
    assert "Type=oneshot" in result.stdout


def test_the_alias_install_without_yes_refuses(
    runner, installed_job_provider, temp_home
):
    # Arrange
    # Act
    result = runner.invoke(main, _ARGV + ["install"])
    # Assert
    assert result.exit_code == 2


def test_the_alias_uninstall_removes_the_units(
    runner, installed_job_provider, temp_home
):
    # Arrange
    runner.invoke(main, _ARGV + ["install", "--name", "testpkg.sysjob", "--yes"])
    # Act
    runner.invoke(main, _ARGV + ["uninstall", "--name", "testpkg.sysjob", "--yes"])
    # Assert
    assert not (temp_home / "testpkg.sysjob.timer").exists()


# EOF
