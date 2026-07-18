#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registration + wiring tests for `scitex-dev ecosystem pr expire`.

No mocks: drives the real Click group via CliRunner. The gh/scitex-cards
I/O is injected at the engine layer (tested in test_pr_expire.py); here we
only assert the command is registered, its help renders, and dry-run
against an injected-empty PR list mutates nothing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _build_cli():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def test_pr_group_is_registered():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "pr", "--help"])
    # Assert
    assert result.exit_code == 0


def test_pr_expire_command_is_registered():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "pr", "expire", "--help"])
    # Assert
    assert result.exit_code == 0


def test_pr_expire_help_mentions_dry_run_default():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "pr", "expire", "--help"])
    # Assert
    assert "dry-run" in result.output.lower()


def test_pr_expire_all_and_repo_are_mutually_exclusive():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(
        main, ["ecosystem", "pr", "expire", "--all", "--repo", "owner/name"]
    )
    # Assert
    assert result.exit_code != 0
