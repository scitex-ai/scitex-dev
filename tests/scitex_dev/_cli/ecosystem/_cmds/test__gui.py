#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registration + behaviour tests for `scitex-dev ecosystem gui`.

No mocks: drives the real Click group via CliRunner. `gui open` is
exercised with --dry-run so no browser is ever launched.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _build_cli():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def test_gui_group_is_registered():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "--help"])
    # Assert
    assert result.exit_code == 0


def test_gui_list_json_exit_code_zero():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "list", "--json"])
    # Assert
    assert result.exit_code == 0


def test_gui_list_json_returns_all_six_packages():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "list", "--json"])
    payload = json.loads(result.output)
    # Assert
    assert len(payload["surfaces"]) == 6


def test_gui_open_dry_run_prints_actual_port_url():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "open", "--dry-run"])
    # Assert
    assert "http://localhost:8051/" in result.output


def test_gui_open_dry_run_does_not_open_browser():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "open", "--dry-run"])
    # Assert
    assert "opening" not in result.output


def test_gui_audit_is_registered():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "audit", "--help"])
    # Assert
    assert result.exit_code == 0


def test_gui_audit_exit_nonzero_while_migrations_pending():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "audit", "--json"])
    # Assert
    assert result.exit_code == 1


def test_gui_audit_json_reports_cards_pending_migration():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "audit", "--json"])
    payload = json.loads(result.output)
    # Assert
    assert any(
        f["package"] == "scitex-cards" and f["kind"] == "pending-migration"
        for f in payload["findings"]
    )


def test_gui_audit_has_no_reservation_violations_on_correct_registry():
    # Arrange
    main = _build_cli()
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "gui", "audit", "--json"])
    payload = json.loads(result.output)
    # Assert
    assert payload["errors"] == 0
