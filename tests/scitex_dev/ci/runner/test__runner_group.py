"""Tests for ``scitex_dev.ci.runner._runner_group``."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._runner_group import register


class TestRunnerGroupRegistration:
    """Test that the runner click group registers correctly."""

    def test_returns_runner_group(self):
        parent = click.Group()
        result = register(parent)
        assert isinstance(result, click.Group)

    def test_runner_group_is_registered_as_subcommand(self):
        parent = click.Group()
        register(parent)
        cmd = parent.get_command(click.Context(parent), "runner")
        assert cmd is not None
        assert isinstance(cmd, click.Group)

    def test_runner_has_status_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "status")
        assert cmd is not None

    def test_runner_has_use_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "use")
        assert cmd is not None

    def test_runner_has_up_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "up")
        assert cmd is not None

    def test_runner_has_down_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "down")
        assert cmd is not None

    def test_runner_has_renew_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "renew")
        assert cmd is not None

    def test_runner_has_onboard_subcommand(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "onboard")
        assert cmd is not None

    def test_runner_verb_help_contains_expected_text(self):
        parent = click.Group()
        runner = register(parent)
        cmd = runner.get_command(click.Context(runner), "status")
        assert cmd is not None
        assert "CI_RUNS_ON" in cmd.help

    def test_use_command_is_leaf_with_target_argument(self):
        parent = click.Group()
        runner = register(parent)
        use = runner.get_command(click.Context(runner), "use")
        assert use is not None
        assert isinstance(use, click.Command)
        assert not isinstance(use, click.Group)
        arg_names = [p.name for p in use.params if isinstance(p, click.Argument)]
        assert "target" in arg_names
