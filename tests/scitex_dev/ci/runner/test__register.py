"""Smoke tests for the ``scitex-dev ci runner`` command group.

No mocks: builds the real click group via ``register_ci_runner_commands``
and invokes ``--help`` on each subcommand through ``CliRunner``, asserting
the command wiring imports and renders. This guards against import errors,
broken decorators, and missing options without exercising any side effects.
"""

from __future__ import annotations

import json

import click
import pytest
from click.testing import CliRunner

from scitex_dev.ci.runner import register_ci_runner_commands

RUNNER_SUBCOMMANDS = [
    "status",
    "use",
    "up",
    "down",
    "renew",
    "register",
    "preflight",
]


def _build_root_group() -> click.Group:
    @click.group()
    def root() -> None:
        pass

    register_ci_runner_commands(root)
    return root


def test_ci_runner_group_help_exits_zero() -> None:
    # Arrange
    root = _build_root_group()
    # Act
    result = CliRunner().invoke(root, ["ci", "runner", "--help"])
    # Assert
    assert result.exit_code == 0


@pytest.mark.parametrize("subcommand", RUNNER_SUBCOMMANDS)
def test_ci_runner_each_subcommand_help_exits_zero(subcommand: str) -> None:
    # Arrange
    root = _build_root_group()
    # Act
    result = CliRunner().invoke(root, ["ci", "runner", subcommand, "--help"])
    # Assert
    assert result.exit_code == 0


def test_ci_runner_register_help_lists_yes_flag() -> None:
    # Arrange
    root = _build_root_group()
    # Act
    result = CliRunner().invoke(root, ["ci", "runner", "register", "--help"])
    # Assert
    assert "--yes" in result.output


def test_ci_runner_register_help_declares_ci_template_alias() -> None:
    # register is a THIN ALIAS of the canonical mechanism (ecosystem
    # ci-template apply) — its help must say so, not describe a second
    # template body.
    # Arrange
    root = _build_root_group()
    # Act
    result = CliRunner().invoke(root, ["ci", "runner", "register", "--help"])
    # Assert
    assert "ci-template" in result.output


def test_ci_runner_register_default_names_the_os_and_arch() -> None:
    """The default must carry the labels GitHub AUTO-ASSIGNS, not just ours.

    REPLACES a literal-equality pin (`assert actual == '["self-hosted",
    "Linux","X64","scitex-ci"]'`). That test asserted that today's value equals
    today's value: it could only ever fail on a deliberate edit, and it dutifully
    passed for the three days in which `scitex-ci` had no online carrier at org
    scope. It also had to be edited by the very change that FIXED the defect,
    which is the signature of a pin that measures nothing.

    What survives is the half that is a real invariant: a runner's EFFECTIVE
    label set includes `self-hosted` / `Linux` / `X64`, so a default naming only
    the custom label would fail to match a workflow written in the fleet idiom.

    Whether the custom label is SERVED is checked against the host registry in
    `test__runs_on_default.py`, which is the question this test used to look
    like it was asking.
    """
    # Arrange
    from scitex_dev.ci.runner._register import CI_RUNS_ON_DEFAULT

    auto_assigned = {"self-hosted", "Linux", "X64"}
    # Act
    labels = set(json.loads(CI_RUNS_ON_DEFAULT))
    # Assert
    assert auto_assigned <= labels, (
        f"CI_RUNS_ON default {sorted(labels)} omits {sorted(auto_assigned - labels)}; "
        "a job naming those would then read as unserved on our own runners"
    )


def test_preflight_required_label_picks_non_builtin() -> None:
    # Arrange
    from scitex_dev.ci.runner._preflight import _required_label

    cfg = {"runner": {"labels": ["self-hosted", "Linux", "X64", "spartan-cpu"]}}
    # Act
    label = _required_label(cfg)
    # Assert — the descriptive label, not GitHub's built-in runner labels.
    assert label == "spartan-cpu"


def test_preflight_required_label_falls_back_to_head_when_all_builtin() -> None:
    # Arrange
    from scitex_dev.ci.runner._preflight import _required_label

    cfg = {"runner": {"labels": ["self-hosted", "Linux"]}}
    # Act
    label = _required_label(cfg)
    # Assert — degenerate config (only builtins) returns the list head.
    assert label == "self-hosted"
