"""Opt-in input errors preserve legacy defaults and valid dispatch results."""

import importlib
import json

import pytest

from scitex_dev.linter.checker import lint_file, lint_source
from scitex_dev.linter.config import load_config
from scitex_dev.linter.formatter import to_json


@pytest.fixture(params=["python", "notebook-json", "notebook-code", "markdown", "rst", "text", "missing", "directory"])
def input_error_case(request, tmp_path):
    invalid = "def broken(\n"
    cases = {
        "python": (".py", invalid),
        "notebook-json": (".ipynb", "{broken JSON"),
        "notebook-code": (".ipynb", json.dumps({"cells": [{"cell_type": "code", "source": [invalid]}]})),
        "markdown": (".md", "```python\n" + invalid + "```\n"),
        "rst": (".rst", ".. code-block:: python\n\n    def broken(\n"),
        "text": (".txt", invalid),
        "missing": (".missing", None),
        "directory": (".directory", None),
    }
    suffix, content = cases[request.param]
    file = tmp_path / ("owned" + suffix)
    if request.param == "directory":
        file.mkdir()
    elif content is not None:
        file.write_text(content)
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    return str(file)


def test_legacy_file_input_defaults_remain_empty(input_error_case):
    # Arrange
    # Act
    result = lint_file(input_error_case)
    # Assert
    assert result == []


def test_file_input_error_optin_raises(input_error_case):
    # Arrange
    # Act
    # Assert
    with pytest.raises((ValueError, OSError)):
        lint_file(input_error_case, raise_input_errors=True)


@pytest.fixture(params=[".py", ".txt", ".ipynb", ".md", ".rst"])
def valid_input_case(request, tmp_path):
    source = 'import requests\nrequests.get("https://owned.invalid")\n'
    contents = {
        ".py": source,
        ".txt": source,
        ".ipynb": json.dumps({"cells": [{"cell_type": "code", "source": source.splitlines(keepends=True)}]}),
        ".md": "```python\n" + source + "```\n",
        ".rst": ".. code-block:: python\n\n    import requests\n    requests.get(\"https://owned.invalid\")\n",
    }
    file = tmp_path / ("valid" + request.param)
    file.write_text(contents[request.param])
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    return str(file), load_config(str(file))


def test_file_input_optin_preserves_valid_findings(valid_input_case):
    # Arrange
    file, config = valid_input_case
    expected = to_json(lint_file(file, config=config), file)
    # Act
    actual = to_json(lint_file(file, config=config, raise_input_errors=True), file)
    # Assert
    assert actual == expected


@pytest.fixture(params=[("_ipynb", "lint_ipynb"), ("_md", "lint_md"), ("_rst", "lint_rst")])
def absent_handler_input(request, tmp_path):
    module, name = request.param
    handler = getattr(importlib.import_module("scitex_dev.linter." + module), name)
    return handler, tmp_path / "missing-input"


def test_handler_read_error_default_is_unchanged(absent_handler_input):
    # Arrange
    handler, path = absent_handler_input
    # Act
    result = handler(path)
    # Assert
    assert result == []


def test_handler_read_error_optin_is_visible(absent_handler_input):
    # Arrange
    handler, path = absent_handler_input
    # Act
    # Assert
    with pytest.raises(FileNotFoundError):
        handler(path, raise_input_errors=True)


def test_source_syntax_error_default_is_unchanged():
    # Arrange
    source = "def broken(\n"
    # Act
    result = lint_source(source)
    # Assert
    assert result == []


def test_source_syntax_error_optin_is_visible():
    # Arrange
    source = "def broken(\n"
    # Act
    # Assert
    with pytest.raises(ValueError, match="Python source could not be parsed"):
        lint_source(source, raise_input_errors=True)


def test_source_optin_preserves_parseable_findings(tmp_path):
    # Arrange
    source = 'raise RuntimeError("never execute")\n'
    file = str(tmp_path / "label.py")
    expected = to_json(lint_source(source, filepath=file), file)
    # Act
    actual = to_json(lint_source(source, filepath=file, raise_input_errors=True), file)
    # Assert
    assert actual == expected


@pytest.fixture(params=[".ipynb", ".md", ".rst"])
def late_input_error_case(request, tmp_path):
    valid = 'import requests\nrequests.get("https://owned.invalid")\n'
    invalid = "def broken(\n"
    cases = {
        ".ipynb": json.dumps({"cells": [
            {"cell_type": "code", "source": valid.splitlines(keepends=True)},
            {"cell_type": "code", "source": [invalid]},
        ]}),
        ".md": "```python\n" + valid + "```\n\n```python\n" + invalid + "```\n",
        ".rst": ".. code-block:: python\n\n    import requests\n    requests.get(\"https://owned.invalid\")\n\n.. code-block:: python\n\n    def broken(\n",
    }
    file = tmp_path / ("late-error" + request.param)
    file.write_text(cases[request.param])
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    return str(file)


def test_legacy_late_input_errors_keep_earlier_findings(late_input_error_case):
    # Arrange
    # Act
    issues = lint_file(late_input_error_case)
    # Assert
    assert [issue.rule.id for issue in issues] == ["STX-NET001"]


def test_optin_late_input_error_does_not_return_partial_findings(late_input_error_case):
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="::(?:cell|block)-1"):
        lint_file(late_input_error_case, raise_input_errors=True)
