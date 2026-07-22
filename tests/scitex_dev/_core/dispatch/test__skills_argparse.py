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


# --- EXECUTION tests -------------------------------------------------
# The parse-only tests above cannot catch a broken function-local import:
# they never call `args.func`, so the module imports cleanly and the
# failure only appears at RUN time. These tests dispatch through the real
# execution path, which is what regressed when the `dispatch.py` ->
# `dispatch/` split left these imports at the flat-module `..` depth
# (resolving to the non-existent `scitex_dev._core._ecosystem`).


def _make_real_package_parser():
    """Parser bound to `scitex-dev`, which registers a real
    `scitex_dev.skills` entry point, so execution resolves genuine
    skills with no mocking."""
    root = argparse.ArgumentParser(prog="scitex-dev")
    subparsers = root.add_subparsers(dest="command")
    register_skills_subcommand(subparsers, package="scitex-dev")
    return root


def test_skills_list_executes_real_dispatch_path(capsys):
    # Arrange
    parser = _make_real_package_parser()
    args = parser.parse_args(["skills", "list"])
    # Act — the call the parse-only tests never made
    args.func(args)
    # Assert
    assert capsys.readouterr().out.strip()


def test_skills_get_without_name_executes_and_lists(capsys):
    # Arrange
    parser = _make_real_package_parser()
    args = parser.parse_args(["skills", "get"])
    # Act
    args.func(args)
    # Assert
    assert capsys.readouterr().out.strip()


def test_skills_export_dry_run_executes(capsys):
    # Arrange — --dry-run reaches the import sites but writes nothing.
    parser = _make_real_package_parser()
    args = parser.parse_args(["skills", "export", "--dry-run"])
    # Act
    args.func(args)
    # Assert
    assert "Would export" in capsys.readouterr().out


def test_skills_backing_module_lives_under_the_package_root():
    """Pin the exact defect: the helpers must resolve `_ecosystem`
    under `scitex_dev`, never under `scitex_dev._core`."""
    # Arrange
    import importlib

    # Act
    real = importlib.import_module("scitex_dev._ecosystem._skills.skills")
    # Assert
    assert real.__name__ == "scitex_dev._ecosystem._skills.skills"


def test_skills_backing_module_is_absent_under_core():
    # Arrange
    import importlib

    # Act
    found = importlib.util.find_spec("scitex_dev._core._ecosystem")
    # Assert
    assert found is None
