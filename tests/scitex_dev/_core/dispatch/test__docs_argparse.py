"""Tests for `register_docs_subcommand` (`_docs_argparse.py`, argparse flavor).

No mocks: builds a REAL `argparse.ArgumentParser` + subparsers tree and
parses argv through it. This module had zero test coverage before the
`dispatch.py` -> `dispatch/` package split (2026-07-11,
CLI-standardization audit pass) -- these are the first tests for it.
"""

from __future__ import annotations

import argparse

from scitex_dev._core.dispatch import register_docs_subcommand


def _make_parser():
    root = argparse.ArgumentParser(prog="scitex-fake-pkg")
    subparsers = root.add_subparsers(dest="command")
    register_docs_subcommand(subparsers, package="scitex-fake-pkg")
    return root


def test_docs_list_parses_without_error():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["docs", "list"])
    # Assert
    assert args.command == "docs" and args.docs_command == "list"


def test_docs_get_parses_page_name():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["docs", "get", "api"])
    # Assert
    assert args.name == "api"


def test_docs_get_json_flag_parses():
    # Arrange
    parser = _make_parser()
    # Act
    args = parser.parse_args(["docs", "get", "api", "--json"])
    # Assert
    assert args.as_json is True
