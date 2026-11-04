"""Recursive projections retain native Click visibility and missing policy."""

import json

import click
from click.testing import CliRunner

from scitex_dev._cli._root_help import _show_recursive_help


class MissingGroup(click.Group):
    def list_commands(self, ctx):
        return [*super().list_commands(ctx), "unavailable"]


class HiddenGroup(click.Group):
    def list_commands(self, ctx):
        raise RuntimeError("hidden group must not be enumerated")


def _tree():
    @click.group(cls=MissingGroup, invoke_without_command=True)
    @click.option("--json", "as_json", is_flag=True)
    @click.pass_context
    def root(ctx, as_json):
        ctx.obj = {"json": as_json}
        _show_recursive_help(ctx)

    @root.command()
    def visible():
        """Public leaf help."""

    @root.group(cls=MissingGroup)
    def nested():
        """Public nested help."""

    @nested.command()
    def child():
        """Public nested leaf."""

    root.add_command(HiddenGroup("private-root", hidden=True))
    nested.add_command(HiddenGroup("private-nested", hidden=True))
    return root


def test_plain_recursive_help_omits_hidden_and_unavailable_commands():
    # Arrange
    root = _tree()
    # Act
    result = CliRunner().invoke(root, [])
    # Assert
    assert (
        result.exit_code,
        "Public leaf help" in result.stdout,
        "Public nested leaf" in result.stdout,
        "private-root" in result.stdout,
        "private-nested" in result.stdout,
        "unavailable" in result.stdout,
    ) == (0, True, True, False, False, False)


def test_json_recursive_help_omits_hidden_and_unavailable_commands():
    # Arrange
    root = _tree()
    # Act
    result = CliRunner().invoke(root, ["--json"])
    tree = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        set(tree["commands"]),
        set(tree["commands"]["nested"]["commands"]),
    ) == (0, {"nested", "visible"}, {"child"})
