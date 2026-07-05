#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registration / help smoke tests for `ecosystem drift-report`.

The command body does real I/O (PyPI, SSH via packages_audit, the `sac`
subprocess), so it is NOT invoked here — the aggregation logic it feeds is
fully covered by the pure engine tests under
`tests/scitex_dev/_ecosystem/_drift_report/`. These tests exercise only
the network-free wiring (registration + `--help`, which never runs the
callback), catching import / option-definition regressions.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _build_group():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def test_drift_report_is_registered_on_the_ecosystem_group():
    # Arrange
    main = _build_group()
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "--help"])
    # Assert
    assert "drift-report" in result.output


def test_drift_report_help_describes_the_layer_matrix():
    # Arrange
    main = _build_group()
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "drift-report", "--help"])
    # Assert
    assert "layer" in result.output.lower()


def test_drift_report_help_documents_json_flag():
    # Arrange
    main = _build_group()
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "drift-report", "--help"])
    # Assert
    assert "--json" in result.output
