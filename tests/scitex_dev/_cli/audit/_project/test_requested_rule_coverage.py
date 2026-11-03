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
    result = _run(tmp_path, ["PS-UNREGISTERED-OWNED-FIXTURE"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "not-auditable"
    assert payload["unavailable_rules"] == ["PS-UNREGISTERED-OWNED-FIXTURE"]


def test_mixed_available_and_unavailable_rules_also_refuse(tmp_path):
    result = _run(tmp_path, ["PS-101", "PS-UNREGISTERED-OWNED-FIXTURE"])
    assert result.exit_code == 2, result.output


def test_registered_rule_can_return_a_clean_verdict(tmp_path):
    result = _run(tmp_path, ["PS-101"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["violations"] == []
