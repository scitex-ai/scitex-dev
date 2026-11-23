"""Actual formatter CLI JSON results preserve preview and apply semantics."""

import json

import pytest
from click.testing import CliRunner

from scitex_dev.linter.cli import main_group


@pytest.fixture(params=[
    ("python", ["--check"], 1, False),
    ("python", ["--dry-run"], 0, False),
    ("python", [], 0, True),
    ("python", ["--diff"], 0, True),
    ("python", ["--dry-run", "--diff"], 0, False),
    ("python", ["--check", "--dry-run"], 1, False),
    ("clean", [], 0, False),
    ("empty", [], 0, False),
    ("missing", [], 2, False),
    ("notebook", ["--check"], 1, False),
    ("notebook", ["--dry-run", "--diff"], 0, False),
    ("notebook", [], 0, True),
    ("clean-notebook", [], 0, False),
])
def format_case(request, tmp_path):
    kind, flags, code, written = request.param
    path = tmp_path / "owned"
    original = 'ax.set_xlabel("x", fontsize=12)\n'
    fixed = 'ax.set_xlabel("x")\n'
    changed = kind in {"python", "notebook"}
    notebook = kind in {"notebook", "clean-notebook"}
    if kind == "empty":
        path.mkdir()
    elif kind != "missing":
        path = path.with_suffix(".ipynb" if notebook else ".py")
        content = original if changed else fixed
        if notebook:
            content = json.dumps({"cells": [
                {"cell_type": "markdown", "source": [original], "metadata": {}},
                {"cell_type": "code", "source": [content], "metadata": {}, "outputs": []},
            ], "metadata": {"owned": True}, "nbformat": 4, "nbformat_minor": 5})
        path.write_text(content)
    before = None
    if path.is_file():
        info = path.stat()
        before = (path.read_bytes(), info.st_ino, info.st_mtime_ns)
    rows = []
    expected_state = (kind == "empty", [])
    if before is not None:
        delta = None
        if "--diff" in flags and changed and not notebook:
            delta = (f"--- {path}\n+++ {path}\n@@ -1 +1 @@\n"
                     '-ax.set_xlabel("x", fontsize=12)\n'
                     '+ax.set_xlabel("x")\n')
        rows = [{"file": str(path), "changed": changed, "written": written, "diff": delta}]
        if written and notebook:
            document = json.loads(before[0])
            document["cells"][1]["source"] = [fixed]
            expected_state = document
        elif written:
            expected_state = fixed
        else:
            expected_state = before
    expected = {
        "path": str(path), "check": "--check" in flags,
        "dry_run": "--dry-run" in flags, "diff": "--diff" in flags,
        "files": rows,
        "summary": {"files": int(before is not None), "changed": int(changed), "written": int(written)},
        "error": f"{path} not found" if kind == "missing" else None,
    }
    return path, flags, code, written, notebook, before, expected, expected_state


@pytest.fixture
def formatted_case(format_case):
    path, flags, code, written, notebook, before, expected, expected_state = format_case
    result = CliRunner().invoke(main_group, ["format-files", str(path), "--json", *flags])
    actual_state = (path.exists(), sorted(path.iterdir()) if path.is_dir() else [])
    if before is not None:
        if written and notebook:
            actual_state = json.loads(path.read_text())
        elif written:
            actual_state = path.read_text()
        else:
            info = path.stat()
            actual_state = (path.read_bytes(), info.st_ino, info.st_mtime_ns)
    return result, code, expected, actual_state, expected_state


def test_format_json_exit_code(formatted_case):
    # Arrange
    result, code, _, _, _ = formatted_case
    # Act
    actual = result.exit_code
    # Assert
    assert actual == code


def test_format_json_complete_document(formatted_case):
    # Arrange
    result, _, expected, _, _ = formatted_case
    # Act
    actual = json.loads(result.stdout)
    # Assert
    assert actual == expected


def test_format_json_file_effects(formatted_case):
    # Arrange
    _, _, _, actual_state, expected_state = formatted_case
    # Act
    # Assert
    assert actual_state == expected_state
