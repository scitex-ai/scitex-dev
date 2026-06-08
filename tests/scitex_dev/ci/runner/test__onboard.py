"""Tests for ``scitex_dev.ci.runner._onboard`` — click group structure only."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._onboard import register


class TestOnboardGroupRegistration:
    """Test that the onboard click command registers correctly."""

    @pytest.fixture(autouse=True)
    def _register_onboard(self, monkeypatch):
        monkeypatch.setenv("SCITEX_DEV_GH_PAT", "fake-token")

    def test_register_returns_none(self):
        parent = click.Group()
        result = register(parent)
        assert result is None

    def test_registered_as_onboard_command(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        onboard_cmd = runner.get_command(click.Context(runner), "onboard")
        assert onboard_cmd is not None

    def test_onboard_command_has_dry_run_option(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        onboard_cmd = runner.get_command(click.Context(runner), "onboard")
        option_names = [p.name for p in onboard_cmd.params if isinstance(p, click.Option)]
        assert "dry_run" in option_names

    def test_onboard_command_has_workflow_name_option(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        onboard_cmd = runner.get_command(click.Context(runner), "onboard")
        option_names = [p.name for p in onboard_cmd.params if isinstance(p, click.Option)]
        assert "workflow_name" in option_names
