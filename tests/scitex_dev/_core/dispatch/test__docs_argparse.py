"""Tests for `register_docs_subcommand` (`_docs_argparse.py`, argparse flavor).

No mocks: builds a REAL `argparse.ArgumentParser` + subparsers tree and
parses argv through it. This module had zero test coverage before the
`dispatch.py` -> `dispatch/` package split (2026-07-11,
CLI-standardization audit pass) -- these are the first tests for it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


# --- EXECUTION tests -------------------------------------------------
# The parse-only tests above never call `args.func`, so they cannot catch
# a broken function-local import. `_docs_argparse` carried the same
# flat-module `..` depth as `_skills_argparse` after the `dispatch.py` ->
# `dispatch/` split, resolving to the non-existent
# `scitex_dev._core._docs`. These tests dispatch for real.


def _make_real_package_parser():
    """Parser bound to `scitex-dev`, which registers a real
    `scitex_dev.docs` entry point, so execution resolves genuine docs."""
    root = argparse.ArgumentParser(prog="scitex-dev")
    subparsers = root.add_subparsers(dest="command")
    register_docs_subcommand(subparsers, package="scitex-dev")
    return root


def test_docs_list_executes_real_dispatch_path(capsys):
    # Arrange
    parser = _make_real_package_parser()
    args = parser.parse_args(["docs", "list"])
    # Act
    args.func(args)
    # Assert
    assert capsys.readouterr().out.strip()


def test_docs_backing_module_is_absent_under_core():
    # Arrange
    import importlib

    # Act
    found = importlib.util.find_spec("scitex_dev._core._docs")
    # Assert
    assert found is None


PROGRAM = r"""
import argparse, json, os, sys
from pathlib import Path
coverage_file = os.environ.get("COVERAGE_FILE")
coverage_base = Path(coverage_file).resolve() if coverage_file else None

def refuse(event, args):
    if event == 'sqlite3.connect':
        database = Path(args[0]).resolve()
        owned_coverage = coverage_base is not None and database.parent == coverage_base.parent and (
            database.name == coverage_base.name or database.name.startswith(coverage_base.name + '.')
        )
        if not owned_coverage:
            raise RuntimeError('Only the conftest-owned coverage shard may use SQLite')
    if event in {'socket.connect', 'socket.bind',
                 'subprocess.Popen', 'os.system', 'os.kill'}:
        raise RuntimeError('Owned documentation CLI refuses external effects')
sys.addaudithook(refuse)
from scitex_dev.cli import docs_click_group, register_docs_subcommand
arguments = json.loads(sys.argv[2])
if sys.argv[1] == 'argparse':
    parser = argparse.ArgumentParser(prog='owned')
    subparsers = parser.add_subparsers(dest='command')
    register_docs_subcommand(subparsers, package='scitex-owned-doc-output')
    args = parser.parse_args(arguments)
    args.func(args)
else:
    import click
    root = click.Group('owned')
    root.add_command(docs_click_group(package='scitex-owned-doc-output'))
    root.main(args=arguments, prog_name='owned')
"""


@pytest.fixture
def docs_site(tmp_path):
    site = tmp_path / "site"
    package = site / "owned_doc_output"
    html = package / "_sphinx_html"
    html.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    content = "<html><head><title>Owned CLI page</title></head><body><h1>Owned CLI page</h1></body></html>"
    (html / "cli.html").write_text(content)
    metadata = site / "scitex_owned_doc_output-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: scitex-owned-doc-output\nVersion: 1.0\n"
    )
    (metadata / "entry_points.txt").write_text(
        "[scitex_dev.docs]\nscitex-owned-doc-output = owned_doc_output\n"
    )
    return site


def _docs_environment(site, level):
    environment = dict(os.environ, SCITEX_LOGGING_LEVEL=level)
    inherited = [
        str(Path(value).resolve())
        for value in environment.get("PYTHONPATH", "").split(os.pathsep)
        if value
    ]
    environment["PYTHONPATH"] = os.pathsep.join([str(site), *inherited])
    environment["SCITEX_DIR"] = str(site.parent / "state")
    return environment


@pytest.mark.parametrize("adapter", ["argparse", "click"])
@pytest.mark.parametrize("level", ["info", "warning", "critical"])
@pytest.mark.parametrize(
    "arguments,expected", [(["docs", "list"], "cli"), (["docs", "get", "cli"], "Owned CLI page")]
)
def test_human_documentation_is_stdout_at_each_log_level(
    tmp_path, docs_site, adapter, level, arguments, expected
):
    # Arrange
    command = [sys.executable, "-c", PROGRAM, adapter, json.dumps(arguments)]
    # Act
    result = subprocess.run(
        command, cwd=tmp_path, env=_docs_environment(docs_site, level), capture_output=True,
        text=True, timeout=20, check=False,
    )
    # Assert
    assert (result.returncode, expected in result.stdout) == (0, True), result.stderr


@pytest.mark.parametrize("adapter", ["argparse", "click"])
@pytest.mark.parametrize("level", ["info", "warning", "critical"])
def test_structured_documentation_keeps_json_stdout(
    tmp_path, docs_site, adapter, level
):
    # Arrange
    command = [
        sys.executable, "-c", PROGRAM, adapter,
        json.dumps(["docs", "list", "--json"]),
    ]
    # Act
    result = subprocess.run(
        command, cwd=tmp_path, env=_docs_environment(docs_site, level), capture_output=True,
        text=True, timeout=20, check=False,
    )
    # Assert
    assert result.returncode == 0 and json.loads(result.stdout)["pages"], result.stderr


@pytest.mark.parametrize("adapter", ["argparse", "click"])
@pytest.mark.parametrize("arguments", [
    ["docs", "get", "missing-owned-page"],
    ["docs", "get", "missing-owned-page", "--format", "html"],
    ["docs", "get", "missing-owned-page", "--format", "json"],
])
def test_missing_named_page_is_a_cli_error(tmp_path, docs_site, adapter, arguments):
    # Arrange
    # Act
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM, adapter, json.dumps(arguments)],
        cwd=tmp_path, env=_docs_environment(docs_site, "warning"),
        capture_output=True, text=True, timeout=20, check=False,
    )
    # Assert
    assert (result.returncode, result.stdout, "missing-owned-page" in result.stderr) == (
        2, "", True
    ), result.stderr


@pytest.mark.parametrize("adapter", ["argparse", "click"])
@pytest.mark.parametrize("arguments", [
    ["docs", "get", "directory-owned-page"],
    ["docs", "get", "directory-owned-page", "--format", "html"],
    ["docs", "get", "directory-owned-page", "--format", "json"],
])
def test_page_directory_is_reported_as_missing(tmp_path, docs_site, adapter, arguments):
    # Arrange
    html = docs_site / "owned_doc_output" / "_sphinx_html"
    for suffix in [".html", ".fjson", ".json"]:
        (html / ("directory-owned-page" + suffix)).mkdir()
    # Act
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM, adapter, json.dumps(arguments)],
        cwd=tmp_path, env=_docs_environment(docs_site, "warning"),
        capture_output=True, text=True, timeout=20, check=False,
    )
    # Assert
    assert (result.returncode, result.stdout, "not found" in result.stderr) == (
        2, "", True
    ), result.stderr


@pytest.mark.parametrize("adapter", ["argparse", "click"])
@pytest.mark.parametrize("format", ["html", "json"])
def test_external_page_is_a_cli_missing_page(tmp_path, docs_site, adapter, format):
    # Arrange
    suffix = ".fjson" if format == "json" else ".html"
    outside = tmp_path / ("outside-page" + suffix)
    outside.write_text(json.dumps({"body": "Outside content sentinel"}))
    arguments = ["docs", "get", str(outside.with_suffix("")), "--format", format]
    # Act
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM, adapter, json.dumps(arguments)],
        cwd=tmp_path, env=_docs_environment(docs_site, "warning"),
        capture_output=True, text=True, timeout=20, check=False,
    )
    # Assert
    assert (result.returncode, result.stdout, "not found" in result.stderr) == (
        2, "", True
    ), result.stderr
