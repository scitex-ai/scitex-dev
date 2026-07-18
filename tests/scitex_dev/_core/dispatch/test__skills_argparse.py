"""Tests for `register_skills_subcommand` (`_skills_argparse.py`, argparse flavor).

No mocks: builds a REAL `argparse.ArgumentParser` + subparsers tree and
parses argv through it. This module had zero test coverage before the
`dispatch.py` -> `dispatch/` package split (2026-07-11,
CLI-standardization audit pass) -- these are the first tests for it.
"""

from __future__ import annotations

import argparse

from scitex_dev._core.dispatch import register_skills_subcommand


def _make_parser():
    root = argparse.ArgumentParser(prog="scitex-fake-pkg")
    subparsers = root.add_subparsers(dest="command")
    register_skills_subcommand(subparsers, package="scitex-fake-pkg")
    return root


def test_skills_list_parses_without_error():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["skills", "list"])
    # Assert
    assert args.command == "skills" and args.skills_command == "list"


def test_skills_get_parses_name():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["skills", "get", "test-selection"])
    # Assert
    assert args.name == "test-selection"


def test_skills_export_dry_run_flag_parses():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["skills", "export", "--dry-run"])
    # Assert
    assert args.dry_run is True
