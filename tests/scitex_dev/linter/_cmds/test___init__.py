"""The `scitex-dev linter` Click command package registers real commands.

Drives the actual `register()` entry points against a real Click group --
no mocks -- so the package contract (every module attaches its leaves and
every leaf carries a spec-built help) is enforced where it is declared.
"""

from __future__ import annotations

import click
import click.testing
import pytest

from scitex_dev._ecosystem.help_spec import CliHelp, SpecCommand
from scitex_dev.linter._cmds import _apis, _format, _rules, _run

# Each module's register() and the leaf names it must attach.
REGISTRARS = [
    (_run, ["lint-and-run"]),
    (_apis, ["list-python-apis"]),
    (_format, ["format-files"]),
    (_rules, ["list-rules", "list-rules-all"]),
]

MODULE_IDS = [module.__name__.rsplit(".", 1)[-1] for module, _names in REGISTRARS]


def _fresh_group() -> click.Group:
    @click.group()
    def main() -> None:
        pass

    return main


@pytest.fixture
def registered_group() -> click.Group:
    """A real Click group with every `_cmds` module registered onto it."""
    group = _fresh_group()
    for module, _names in REGISTRARS:
        module.register(group)
    return group


@pytest.mark.parametrize("module,names", REGISTRARS, ids=MODULE_IDS)
def test_register_attaches_its_leaves(module, names):
    # Arrange
    group = _fresh_group()
    # Act
    module.register(group)
    # Assert
    assert [n for n in names if n not in group.commands] == []


def test_every_leaf_is_a_spec_command(registered_group):
    # Arrange
    commands = registered_group.commands
    # Act
    plain = [n for n, c in commands.items() if not isinstance(c, SpecCommand)]
    # Assert -- doctrine 4b: help is spec-built, not free-form text.
    assert plain == []


def test_every_leaf_carries_a_clihelp_spec(registered_group):
    # Arrange
    commands = registered_group.commands
    # Act
    unspecced = [
        n for n, c in commands.items() if not isinstance(c._help_spec, CliHelp)
    ]
    # Assert
    assert unspecced == []


def test_every_leaf_documents_an_example(registered_group):
    # Arrange
    commands = registered_group.commands
    # Act
    exampleless = [n for n, c in commands.items() if not c._help_spec.examples]
    # Assert -- doctrine 4: every leaf shows a concrete invocation.
    assert exampleless == []


def test_examples_use_the_prog_placeholder(registered_group):
    # Arrange
    commands = registered_group.commands
    # Act
    hardcoded = [
        f"{name}: {example.cmd}"
        for name, cmd in commands.items()
        for example in cmd._help_spec.examples
        if "{prog}" not in example.cmd
    ]
    # Assert -- specs stay brand-neutral; the renderer substitutes {prog}.
    assert hardcoded == []


def test_registering_all_modules_yields_no_name_collisions(registered_group):
    # Arrange
    expected = sorted(name for _module, names in REGISTRARS for name in names)
    # Act
    attached = sorted(registered_group.commands)
    # Assert -- a collision would silently shadow a command.
    assert attached == expected


@pytest.mark.parametrize("leaf", ["lint-and-run", "list-rules", "format-files"])
def test_leaf_help_renders_an_examples_section(registered_group, leaf):
    # Arrange
    runner = click.testing.CliRunner()
    # Act
    result = runner.invoke(registered_group, [leaf, "--help"])
    # Assert -- proves the spec-built epilog actually reaches the user.
    assert "Examples:" in result.output


# EOF
