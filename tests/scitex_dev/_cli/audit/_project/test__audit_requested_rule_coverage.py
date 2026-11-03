"""A selected but unavailable rule cannot become a clean verdict."""

import json

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _run(root, rules):
    (root / "pyproject.toml").write_text('[project]\nname="owned-rule-fixture"\n')

    @click.group()
    def command():
        pass

    register_ecosystem_commands(command)
    args = ["ecosystem", "audit-project", "owned-rule-fixture", "--path", str(root), "--json"]
    for rule in rules:
        args.extend(["--rule", rule])
    return CliRunner().invoke(command, args)


def test_unregistered_rule_refuses_a_clean_verdict(tmp_path):
    # Arrange
    requested = ["PS-UNREGISTERED-OWNED-FIXTURE"]
    # Act
    result = _run(tmp_path, requested)
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["status"], payload["unavailable_rules"])
    # Assert
    assert observed == (2, "not-auditable", requested), result.output


def test_mixed_available_and_unavailable_rules_also_refuse(tmp_path):
    # Arrange
    requested = ["PS-101", "PS-UNREGISTERED-OWNED-FIXTURE"]
    # Act
    result = _run(tmp_path, requested)
    # Assert
    assert result.exit_code == 2, result.output


def test_registered_rule_can_return_a_clean_verdict(tmp_path):
    # Arrange
    requested = ["PS-101"]
    # Act
    result = _run(tmp_path, requested)
    observed = (result.exit_code, json.loads(result.stdout)["violations"])
    # Assert
    assert observed == (0, []), result.output
