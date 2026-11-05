"""Actual CLI catalog is parseable metadata, not a live capability assertion."""

import json
import sys

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._docs_cmds import register_docs_commands


def test_provider_catalog_is_structured_and_explicitly_not_live():
    # Arrange
    @click.group()
    def command():
        pass

    register_docs_commands(command)
    # Act
    result = CliRunner().invoke(command, ["docs", "list-providers", "--json"])
    payload = json.loads(result.stdout)
    observed = (
        result.exit_code,
        payload["schema_version"],
        isinstance(payload["providers"], list),
        isinstance(payload["ambiguous_names"], list),
        payload["declarations_only"],
        payload["live_verified"],
    )
    # Assert
    assert observed == (0, "scitex-doc-providers/1", True, True, True, False)


def _docs_cli():
    command = click.Group("owned")
    register_docs_commands(command)
    return command


def _source_project(root):
    package = root / "src/owned_doc_cli_poison"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "owned-doc-cli-poison"\nversion = "1.0.0"\n'
    )
    (package / "__init__.py").write_text(
        'raise RuntimeError("source must not import")\ndef public():\n    pass\n'
    )
    return root


@pytest.mark.parametrize(
    "text,expected_status,expected_exit",
    [
        ("```python\nfrom owned_doc_cli_poison import public\n```\n", "ok", 0),
        (
            "```python\nfrom owned_doc_cli_poison import absent\n```\n",
            "incomplete",
            2,
        ),
        (
            "```python\nfrom owned_doc_cli_poison import (\n```\n",
            "needs_update",
            1,
        ),
        ("Human guidance without Python fences.\n", "incomplete", 2),
    ],
)
def test_validate_reports_actual_static_scope_and_distinct_exit_codes(
    tmp_path, text, expected_status, expected_exit
):
    # Arrange
    root = _source_project(tmp_path)
    document = root / "AGENTS.md"
    document.write_text(text)
    before = {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    # Act
    result = CliRunner().invoke(
        _docs_cli(),
        ["docs", "validate", "--path", str(root), "--document", "AGENTS.md", "--json"],
    )
    payload = json.loads(result.stdout)
    after = {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    # Assert
    assert (
        result.exit_code,
        payload["status"],
        payload["checked_scope"]["documents"],
        bool(payload["limitations"]),
        after == before,
        "owned_doc_cli_poison" in sys.modules,
    ) == (expected_exit, expected_status, [str(document)], True, True, False)


def test_validate_never_executes_documented_statements(tmp_path):
    # Arrange
    root = _source_project(tmp_path)
    sentinel = root / "must-not-exist"
    (root / "README.md").write_text(
        f'```python\nfrom owned_doc_cli_poison import public\nopen({str(sentinel)!r}, "w").write("not permitted")\n```\n'
    )
    # Act
    result = CliRunner().invoke(
        _docs_cli(), ["docs", "validate", "--path", str(root), "--json"]
    )
    payload = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        payload["status"],
        sentinel.exists(),
        payload["checked_scope"]["python_blocks"],
    ) == (0, "ok", False, 1)


@pytest.mark.parametrize("document", ["missing.md", "../outside.md"])
def test_validate_missing_and_outside_documents_report_failure(tmp_path, document):
    # Arrange
    root = _source_project(tmp_path / "package")
    (tmp_path / "outside.md").write_text(
        "Owned outside fixture, not a package document.\n"
    )
    # Act
    result = CliRunner().invoke(
        _docs_cli(),
        ["docs", "validate", "--path", str(root), "--document", document, "--json"],
    )
    payload = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        payload["status"],
        bool(payload["issues"]),
        "Traceback" in result.output,
    ) == (1, "needs_update", True, False)


def test_validate_human_report_keeps_incomplete_scope_visible(tmp_path):
    # Arrange
    root = _source_project(tmp_path)
    (root / "README.md").write_text("Manual-only prose.\n")
    # Act
    result = CliRunner().invoke(_docs_cli(), ["docs", "validate", "--path", str(root)])
    # Assert
    assert (
        result.exit_code,
        "incomplete" in result.stdout,
        "limitations:" in result.stdout,
        "No Python/py fenced blocks were checked" in result.stdout,
    ) == (2, True, True, True)
