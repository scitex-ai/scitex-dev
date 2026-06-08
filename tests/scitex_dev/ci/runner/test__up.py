"""Tests for ``scitex_dev.ci.runner._up`` — click group structure only."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._up import register


class TestUpGroupRegistration:
    """Test that the up click command registers correctly."""

    @pytest.fixture(autouse=True)
    def _register_up(self, monkeypatch):
        monkeypatch.setenv("SCITEX_DEV_GH_PAT", "fake-token")

    def test_register_returns_none(self):
        parent = click.Group()
        result = register(parent)
        assert result is None

    def test_registered_as_up_command(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        up_cmd = runner.get_command(click.Context(runner), "up")
        assert up_cmd is not None

    def test_up_command_has_launcher_option(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        up_cmd = runner.get_command(click.Context(runner), "up")
        option_names = [p.name for p in up_cmd.params if isinstance(p, click.Option)]
        assert "launcher" in option_names

    def test_up_command_has_replace_runner_option(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        up_cmd = runner.get_command(click.Context(runner), "up")
        option_names = [p.name for p in up_cmd.params if isinstance(p, click.Option)]
        assert "replace_runner" in option_names
