"""Tests for ``scitex_dev.ci.runner._down`` — click group structure only."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._down import register


class TestDownGroupRegistration:
    """Test that the down click command registers correctly."""

    @pytest.fixture(autouse=True)
    def _register_down(self, monkeypatch):
        monkeypatch.setenv("SCITEX_DEV_GH_PAT", "fake-token")

    def test_register_returns_none(self):
        parent = click.Group()
        result = register(parent)
        assert result is None

    def test_registered_as_down_command(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        down_cmd = runner.get_command(click.Context(runner), "down")
        assert down_cmd is not None

    def test_down_command_has_runner_name_option(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        down_cmd = runner.get_command(click.Context(runner), "down")
        option_names = [p.name for p in down_cmd.params if isinstance(p, click.Option)]
        assert "runner_name" in option_names
