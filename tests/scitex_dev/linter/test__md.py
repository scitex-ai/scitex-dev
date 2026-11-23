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


@pytest.fixture(params=[(indent, suffix) for indent in [0, 1, 3] for suffix in ["literal", "python", " # comment", " `"]])
def closing_fence_content_case(request, tmp_path):
    indent, suffix = request.param
    prefix = " " * indent
    code = 'TEXT = """\n```' + suffix + '\n"""\nimport requests\nrequests.get("https://owned.invalid")\n'
    text = "# Owned\n\n" + prefix + "```python\n" + "".join(prefix + line for line in code.splitlines(keepends=True)) + prefix + "```\n"
    file = tmp_path / "literal.md"
    file.write_text(text)
    return file, text, code


def test_closing_fence_requires_end_of_line_after_backticks(closing_fence_content_case):
    # Arrange
    _, text, code = closing_fence_content_case
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == [(0, 4, code)]


def test_closing_fence_content_does_not_truncate_python(closing_fence_content_case):
    # Arrange
    file, _, _ = closing_fence_content_case
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", 8)]


@pytest.fixture(params=[(fence, ending) for fence in ["```", "````", "```  ", "````\t"] for ending in ["\n", "\r\n", ""]])
def closing_fence_valid_case(request, tmp_path):
    fence, ending = request.param
    file = tmp_path / "closing.md"
    file.write_text('```py\nimport requests\nrequests.get("https://owned.invalid")\n' + fence + ending)
    return str(file)


def test_closing_fence_valid_lengths_whitespace_and_endings(closing_fence_valid_case):
    # Arrange
    # Act
    issues = lint_file(closing_fence_valid_case, raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", 3)]
