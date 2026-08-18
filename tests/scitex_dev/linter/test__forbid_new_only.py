#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`--new-only` is forbidden, and the refusal must say why.

Operator ruling, 2026-08-18, unprompted and fleet-wide:

    「--new-only は禁止です！！！」
    「いかなるパッケージも、です。」

The flag capped PRE-EXISTING findings to warning so they never blocked
a build. The failure mode is not that debt survives — it is that a
package stops honouring a shared rule WITHOUT ANYONE DECIDING TO, and
the gate keeps reporting green against a smaller rule set than the one
it claims to enforce. Nothing marks the moment it stopped.
"""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from scitex_dev.linter._cmd_check import register
from scitex_dev.linter._forbid_new_only import FORBIDDEN_NEW_ONLY


@pytest.fixture
def cli():
    group = click.Group("linter")
    register(group)
    return group


def test_passing_the_flag_fails(cli):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", ".", "--new-only"])
    # Assert
    assert result.exit_code != 0


def test_the_refusal_quotes_the_ruling(cli):
    """A refusal that does not say why gets worked around, not obeyed."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", ".", "--new-only"])
    # Assert
    assert "禁止" in result.output


def test_the_refusal_names_the_supported_alternative(cli):
    """Otherwise the next move is to disable the gate entirely."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", ".", "--new-only"])
    # Assert
    assert "audit.exemptions" in result.output


def test_the_flag_still_exists_rather_than_being_deleted(cli):
    """Deleting it would say "no such option" — a typo, not a ruling.

    A caller with `--new-only` in a script would then go hunting for the
    correct spelling of a flag that was removed on purpose. Keeping it
    and refusing teaches the rule instead.
    """
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", "--help"])
    # Assert
    assert "--new-only" in result.output


def test_the_help_text_marks_it_forbidden(cli):
    """The reader must learn it is banned BEFORE they try it."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", "--help"])
    # Assert
    assert "FORBIDDEN" in result.output


def test_the_message_explains_the_silent_failure(cli):
    """The reason is the point: it is not "debt is bad"."""
    # Arrange
    message = FORBIDDEN_NEW_ONLY
    # Act
    explains = "stops honouring" in message
    # Assert
    assert explains


def test_omitting_the_flag_does_not_trip_the_refusal(cli):
    """The guard must gate on the FLAG, not on running the command.

    Without this, a refusal that fired unconditionally would look
    identical to a working ban while breaking every ordinary run.
    """
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["validate-files", "--help"])
    # Assert
    assert "FORBIDDEN" in result.output and result.exit_code == 0


# EOF
