"""Tests for ``scitex_dev.ci.runner._use`` — click group structure only."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._use import register


class TestUseGroupRegistration:
    """Test that the use click group registers as a sub-group."""

    @pytest.fixture(autouse=True)
    def _register_use(self, monkeypatch):
        monkeypatch.setenv("SCITEX_DEV_GH_PAT", "fake-token")

    def test_register_returns_none(self):
        parent = click.Group()
        result = register(parent)
        assert result is None

    def test_registered_as_use_subcommand(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        use_cmd = runner.get_command(click.Context(runner), "use")
        assert use_cmd is not None
        assert isinstance(use_cmd, click.Group)
