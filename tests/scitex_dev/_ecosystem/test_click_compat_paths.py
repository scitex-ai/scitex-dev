"""Real lazy Click paths retain policy, callbacks, arguments and help."""

import os

import click
import pytest
from click.testing import CliRunner

from scitex_dev._ecosystem.click_compat import deprecated_alias


@pytest.fixture(autouse=True)
def owned_marker_directory(tmp_path):
    """Keep warning markers inside this test's owned temporary directory."""
    prior = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = prior


class PolicyGroup(click.Group):
    enabled = True

    def get_command(self, ctx, name):
        return (
            super().get_command(ctx, name)
            if self.enabled
            and ctx.command is self
            and ctx.params.get("enabled") is True
            else None
        )


def _cli():
    @click.group()
    def root():
        pass

    @root.group(cls=PolicyGroup)
    @click.option("--enabled/--disabled", default=True)
    @click.pass_context
    def dev(ctx, enabled):
        ctx.ensure_object(dict)
        ctx.obj["initialized"] = True

    @dev.command()
    @click.argument("value")
    @click.option("--code", type=int, default=0)
    @click.pass_context
    def skills(ctx, value, code):
        """Actual skills help."""
        click.echo(f"{value}:{ctx.obj['initialized']}")
        ctx.exit(code)

    alias = deprecated_alias(root, "old", target=("dev", "skills"), remove_in="1.0")
    return root, dev, alias


def test_nested_alias_runs_real_group_and_preserves_output_exit_args():
    # Arrange
    root, _, alias = _cli()
    # Act
    result = CliRunner().invoke(root, ["old", "--code", "7", "hello world"])
    # Assert
    assert (
        result.exit_code,
        result.stdout,
        alias.hidden,
        alias._deprecated_alias["target"],
        "old" in CliRunner().invoke(root, ["--help"]).stdout,
    ) == (7, "hello world:True\n", True, "dev skills", False)


def test_nested_help_forwarded_without_invoking_business_callback():
    # Arrange
    root, _, _ = _cli()
    # Act
    result = CliRunner().invoke(root, ["old", "--help"])
    # Assert
    assert (
        result.exit_code,
        "Actual skills help" in result.stdout,
        "--code" in result.stdout,
    ) == (0, True, True)


def test_disabled_nested_target_refuses_even_help():
    # Arrange
    root, dev, _ = _cli()
    dev.enabled = False
    # Act
    result = CliRunner().invoke(root, ["old", "--help"])
    # Assert
    assert result.exit_code == 2 and "No such command" in result.output


@pytest.mark.parametrize("target", [("missing", "skills"), ("dev", "missing")])
def test_missing_or_non_group_path_refuses(target):
    # Arrange
    root, _, _ = _cli()
    deprecated_alias(root, "bad", target=target, remove_in="1")
    # Act
    result = CliRunner().invoke(root, ["bad"])
    # Assert
    assert result.exit_code == 2


@pytest.mark.parametrize("target", [(), ("",), ("dev skills",), ("dev", 1)])
def test_invalid_paths_refused_at_registration(target):
    # Arrange
    root, _, _ = _cli()
    # Act
    # Assert
    with pytest.raises(ValueError, match="target path"):
        deprecated_alias(root, "bad", target=target, remove_in="1")
