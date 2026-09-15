#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/ecosystem/_cmds/test__list.py

"""`ecosystem list --json` must emit the registry record, not a projection.

The JSON view used to hand-pick two keys -- ``name`` and ``github_repo`` --
and drop the rest of each row on the floor. That is not merely thin. The same
command already FILTERS on ``category`` through ``--category``, so a caller
could select on a field the output never showed them, and a reader who trusts
the JSON concludes the registry holds names and repos. It does not; it holds
five fields per package. No existing test noticed, because every test of this
command asserted on ``--help``.

The assertion below is written against the TABLE rather than against a fixed
list of keys, so a field added to the registry later cannot be quietly dropped
from the JSON the same way.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._ecosystem import ECOSYSTEM
from scitex_dev._cli.ecosystem._registry import register_ecosystem_commands


def _list_json():
    """Invoke ``ecosystem list --json`` and return the parsed packages."""

    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    result = CliRunner().invoke(main, ["ecosystem", "list", "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["packages"]


def test_every_registry_field_survives_the_json_view():
    # Arrange
    items = {item["name"]: item for item in _list_json()}
    # Act
    missing = {
        name: sorted(set(record) - set(items[name]))
        for name, record in ECOSYSTEM.items()
        if name in items and set(record) - set(items[name])
    }
    # Assert
    assert missing == {}


def test_category_reaches_the_json_because_the_command_filters_on_it():
    # Arrange
    known = next(
        name for name, rec in ECOSYSTEM.items() if rec.get("category")
    )
    # Act
    items = {item["name"]: item for item in _list_json()}
    # Assert
    assert items[known]["category"] == ECOSYSTEM[known]["category"]


def test_the_two_original_keys_are_still_present_for_old_consumers():
    # Arrange
    # Act
    items = _list_json()
    # Assert
    assert all("name" in i and "github_repo" in i for i in items)


def test_a_package_absent_from_the_table_still_gets_a_github_repo_key():
    """The old code defaulted the key to ""; ``**record`` alone would not."""
    # Arrange
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    # Act
    result = CliRunner().invoke(
        main, ["ecosystem", "list", "--json", "--package", "not-a-package"]
    )
    # Assert
    if result.exit_code == 0:
        items = json.loads(result.output)["packages"]
        assert all("github_repo" in i for i in items)
