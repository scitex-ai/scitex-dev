"""Tests for `skills_click_group` (`_skills_click.py`).

No mocks: builds a REAL Click group via `click.testing.CliRunner`. Help
output never touches skill-resolution, so these are safe to run without
a real installed package's skills.

This module had zero test coverage before the `dispatch.py` -> `dispatch/`
package split (2026-07-11, CLI-standardization audit pass) -- these are
the first tests for it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._core.dispatch import skills_click_group


def _make_root(package: str = "scitex-fake-pkg"):
    @click.group()
    def root():
        pass

    root.add_command(skills_click_group(package=package))
    return root


def test_skills_group_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["skills", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_list_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["skills", "list", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_get_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["skills", "get", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_export_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_root(), ["skills", "export", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_install_alias_shares_export_help():
    # Arrange -- `install` is a same-callback alias of `export` (§3
    # canonical materialise verb); both must resolve to a real command.
    runner = CliRunner()
    # Act
    export_result = runner.invoke(_make_root(), ["skills", "export", "--help"])
    install_result = runner.invoke(_make_root(), ["skills", "install", "--help"])
    # Assert
    assert export_result.exit_code == 0 and install_result.exit_code == 0


def test_group_exposes_the_federated_subcommands():
    # Arrange -- a leaf gets its whole `skills` verb in one line; the
    # built group must carry the subcommands leaves used to hand-roll.
    group = skills_click_group(package="scitex-fake-pkg")
    # Act
    names = set(group.commands)
    # Assert
    assert {"list", "get", "export", "install"} <= names


def _public_bound_root(namespace):
    from scitex_dev.cli import skills_click_group

    @click.group()
    def root():
        pass

    root.add_command(skills_click_group(package=namespace))
    return root


def test_bound_click_default_retains_ambiguity_refusal(colliding_skill_providers):
    # Arrange
    from scitex_dev.skill_registry import SkillRegistryError

    namespace, _ = colliding_skill_providers
    # Act
    result = CliRunner().invoke(_public_bound_root(namespace), ["skills", "get", "SKILL"])
    # Assert
    assert isinstance(result.exception, SkillRegistryError)


def test_bound_click_owner_read_has_no_imports(colliding_skill_providers):
    # Arrange
    import json

    namespace, marker = colliding_skill_providers
    # Act
    result = CliRunner().invoke(
        _public_bound_root(namespace),
        ["skills", "get", "SKILL", "--owner", "scitex-adapter-current", "--json"],
    )
    # Assert
    assert (
        result.exit_code, json.loads(result.stdout)["content"], marker.exists(),
        (marker.parent / "state").exists(),
    ) == (0, "# Current owner\n", False, False)


def test_bound_click_owner_without_name_reads_index(colliding_skill_providers):
    # Arrange
    import json

    namespace, _ = colliding_skill_providers
    # Act
    result = CliRunner().invoke(
        _public_bound_root(namespace),
        ["skills", "get", "--owner", "scitex-adapter-archived", "--json"],
    )
    # Assert
    assert (result.exit_code, json.loads(result.stdout)["content"]) == (
        0, "# Archived owner\n"
    )


def test_bound_click_wrong_owner_refuses(colliding_skill_providers):
    # Arrange
    namespace, marker = colliding_skill_providers
    # Act
    result = CliRunner().invoke(
        _public_bound_root(namespace),
        ["skills", "get", "SKILL", "--owner", "scitex-adapter-missing", "--json"],
    )
    # Assert
    assert (result.exit_code, result.stdout, marker.exists()) == (2, "", False)


def test_bound_click_without_name_or_owner_keeps_listing():
    # Arrange
    import json

    root = _public_bound_root("scitex-dev")
    # Act
    result = CliRunner().invoke(root, ["skills", "get", "--json"])
    # Assert
    assert (result.exit_code, "scitex-dev" in json.loads(result.stdout)) == (0, True)
