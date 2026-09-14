#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`<pkg> dev access` — exit codes 0/10/11 and the --json record."""

from __future__ import annotations

import json

import click
import jsonschema
import pytest
from click.testing import CliRunner

from scitex_dev.access import load_decision_schema
from scitex_dev.access.cli import register_access_group

from ._world import ALICE_DOC, FIXTURE, PUBLIC_DOC


def _leaf_cli() -> click.Group:
    @click.group()
    def main() -> None:
        pass

    @main.group("dev")
    def dev() -> None:
        pass

    register_access_group(dev, pkg="tests")
    return main


@pytest.fixture
def fixture_file(tmp_path):
    path = tmp_path / "world.json"
    path.write_text(json.dumps(FIXTURE.to_dict()), encoding="utf-8")
    return str(path)


def _invoke(fixture_file: str, *extra: str):
    return CliRunner().invoke(_leaf_cli(), ["dev", "access", *extra, "--fixture", fixture_file])


EXIT_CASES = [
    ("allowed", "user:alice", "edit", ALICE_DOC.ref, 0),
    ("denied", "user:mallory", "view", ALICE_DOC.ref, 10),
    ("not-signed-in", "anonymous", "edit", PUBLIC_DOC.ref, 10),
    ("missing-resource-denied", "user:mallory", "view", "demo.doc:/users/nobody/x", 10),
    ("kind-unregistered", "user:alice", "view", "ghost.thing:/users/alice/g1", 11),
]


@pytest.mark.parametrize(
    "principal, action, resource, expected",
    [case[1:] for case in EXIT_CASES],
    ids=[case[0] for case in EXIT_CASES],
)
def test_check_exits_with_the_decision_exit_code(fixture_file, principal, action, resource, expected):
    # Arrange
    arguments = ("check", "--principal", principal, "--action", action, "--resource", resource)
    # Act
    result = _invoke(fixture_file, *arguments)
    # Assert
    assert result.exit_code == expected


@pytest.mark.parametrize(
    "principal, action, resource, expected",
    [case[1:] for case in EXIT_CASES],
    ids=[case[0] for case in EXIT_CASES],
)
def test_check_json_output_is_a_schema_valid_record(fixture_file, principal, action, resource, expected):
    # Arrange
    arguments = ("check", "--principal", principal, "--action", action, "--resource", resource, "--json")
    result = _invoke(fixture_file, *arguments)
    # Act
    validation = jsonschema.validate(json.loads(result.stdout), load_decision_schema())
    # Assert
    assert validation is None


def test_check_human_output_leads_with_kind_and_reason(fixture_file):
    # Arrange
    arguments = ("check", "--principal", "user:bob", "--action", "edit", "--resource", ALICE_DOC.ref)
    # Act
    result = _invoke(fixture_file, *arguments)
    # Assert
    assert result.stdout.strip() == "allowed grant"


def test_a_malformed_principal_is_a_usage_failure_not_a_decision(fixture_file):
    # Arrange
    arguments = ("check", "--principal", "alice", "--action", "view", "--resource", ALICE_DOC.ref)
    # Act
    result = _invoke(fixture_file, *arguments)
    # Assert
    assert result.exit_code == 1


def test_kinds_json_lists_the_fixture_kinds(fixture_file):
    # Arrange
    arguments = ("list-kinds", "--json")
    # Act
    result = _invoke(fixture_file, *arguments)
    # Assert
    assert [kind["name"] for kind in json.loads(result.stdout)["kinds"]] == ["demo.doc", "demo.project"]


def test_scitex_dev_mounts_access_under_its_dev_group():
    # Arrange
    from scitex_dev._cli import main
    # Act
    result = CliRunner().invoke(main, ["dev", "access", "list-kinds", "--json"])
    # Assert
    assert result.exit_code == 0


# EOF
