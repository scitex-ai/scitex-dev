"""Markdown indentation preserves Python structure and document locations."""

import pytest

from scitex_dev.linter._md import _iter_python_blocks
from scitex_dev.linter.checker import lint_file


@pytest.fixture(params=[(indent, language, uneven) for indent in range(4) for language in ["python", "py"] for uneven in [False, True]])
def indented_python_fence(request, tmp_path):
    indent, language, uneven = request.param
    source = 'import requests\nif True:\n    requests.get("https://owned.invalid")\n'
    lines = source.splitlines(keepends=True)
    content = "".join(("" if uneven and index == 0 else " " * indent) + line for index, line in enumerate(lines))
    markdown = "# Owned\n\n" + " " * indent + "```" + language + "\n" + content + " " * indent + "```\n"
    file = tmp_path / "owned.md"
    file.write_text(markdown)
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\n')
    return file, markdown, source


def test_python_fence_indentation_preserves_nested_body(indented_python_fence):
    # Arrange
    _, markdown, source = indented_python_fence
    # Act
    blocks = list(_iter_python_blocks(markdown))
    # Assert
    assert blocks == [(0, 4, source)]


def test_python_fence_indentation_preserves_findings_and_document_lines(indented_python_fence):
    # Arrange
    file, _, _ = indented_python_fence
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", 6)]


@pytest.fixture(params=range(4))
def extra_indentation_input(request, tmp_path):
    indent = request.param
    file = tmp_path / "extra.md"
    file.write_text(" " * indent + "```python\n" + " " * (indent + 4) + "VALUE = 1\n" + " " * indent + "```\n")
    return str(file)


def test_python_indentation_beyond_fence_remains_an_error(extra_indentation_input):
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="Python source could not be parsed"):
        lint_file(extra_indentation_input, raise_input_errors=True)


def test_python_extra_indentation_keeps_default_behavior(extra_indentation_input):
    # Arrange
    # Act
    issues = lint_file(extra_indentation_input)
    # Assert
    assert issues == []
