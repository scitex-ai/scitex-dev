"""Tests for ``scitex_dev.ci.runner._use`` — click command structure only."""

from __future__ import annotations

import click
import pytest

from scitex_dev.ci.runner._use import register


class TestUseCommandRegistration:
    """Test that the use click command registers as a leaf command."""

    @pytest.fixture(autouse=True)
    def _register_use(self, monkeypatch):
        monkeypatch.setenv("SCITEX_DEV_GH_PAT", "fake-token")

    def test_register_returns_none(self):
        parent = click.Group()
        result = register(parent)
        assert result is None

    def test_registered_as_use_command(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        use_cmd = runner.get_command(click.Context(runner), "use")
        assert use_cmd is not None
        # use is now a click.Command (not a Group)
        assert not isinstance(use_cmd, click.Group)
        assert isinstance(use_cmd, click.Command)

    def test_use_command_has_target_argument(self):
        parent = click.Group()
        runner = click.Group()
        parent.add_command(runner, name="runner")
        register(runner)
        use_cmd = runner.get_command(click.Context(runner), "use")
        arg_names = [p.name for p in use_cmd.params if isinstance(p, click.Argument)]
        assert "target" in arg_names
