"""Tests for ``scitex_dev.ci.runner`` package entry point."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner import register_ci_runner_commands


class TestRegisterCiRunnerCommands:
    """Test the main CLI registration function."""

    def test_returns_click_group(self):
        result = register_ci_runner_commands(click.Group())
        assert isinstance(result, click.Group)

    def test_registers_ci_group_as_subcommand(self):
        main = click.Group()
        register_ci_runner_commands(main)
        ci_cmd = main.get_command(click.Context(main), "ci")
        assert ci_cmd is not None
        assert isinstance(ci_cmd, click.Group)

    def test_ci_group_has_runner_subcommand(self):
        main = click.Group()
        ci = register_ci_runner_commands(main)
        runner_cmd = ci.get_command(click.Context(ci), "runner")
        assert runner_cmd is not None
        assert isinstance(runner_cmd, click.Group)

    def test_ci_group_has_help(self):
        main = click.Group()
        ci = register_ci_runner_commands(main)
        assert ci.help is not None
        assert "runner" in ci.help.lower()

    def test_runner_group_has_help(self):
        main = click.Group()
        ci = register_ci_runner_commands(main)
        runner = ci.get_command(click.Context(ci), "runner")
        assert runner is not None
        assert runner.help is not None
        assert "status" in runner.help.lower()
