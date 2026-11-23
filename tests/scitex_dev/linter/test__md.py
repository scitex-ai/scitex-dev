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


@pytest.fixture(params=[(tag, indent) for tag in ["python-console", "python-repl", "python.notebook", "python!", "py-repl", "py!"] for indent in [0, 2]])
def md_language_tag_case(request, tmp_path):
    tag, indent = request.param
    prefix = " " * indent
    text = prefix + "```" + tag + "\n" + prefix + ">>> not Python code (\n" + prefix + "```\n"
    file = tmp_path / "foreign.md"
    file.write_text(text)
    return file, text


def test_language_tag_md_does_not_extract_prefix_lookalikes(md_language_tag_case):
    # Arrange
    _, text = md_language_tag_case
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == []


def test_language_tag_md_does_not_parse_foreign_text(md_language_tag_case):
    # Arrange
    file, _ = md_language_tag_case
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert issues == []


@pytest.fixture(params=[(tag, indent) for tag in ["python", "py", "PYTHON", "Py", 'python title="owned"', "py\ttitle=owned"] for indent in [0, 2]])
def md_language_tag_valid_case(request, tmp_path):
    tag, indent = request.param
    prefix = " " * indent
    file = tmp_path / "actual.md"
    file.write_text(prefix + "```" + tag + "\n" + prefix + "import requests\n" + prefix + 'requests.get("https://owned.invalid")\n' + prefix + "```\n")
    return str(file)


def test_language_tag_md_keeps_complete_tags_and_metadata(md_language_tag_valid_case):
    # Arrange
    # Act
    issues = lint_file(md_language_tag_valid_case, raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", 3)]


@pytest.fixture(params=[(marker, closed, indent) for marker, closed in [("```", True), ("````", True), ("~~~", True), ("~~~~", True), ("```", False), ("~~~", False)] for indent in [0, 2]])
def fence_scan_python_case(request, tmp_path):
    marker, closed, indent = request.param
    prefix = " " * indent
    code = 'import requests\nrequests.get("https://owned.invalid")\n'
    text = prefix + marker + "python\n" + "".join(prefix + line for line in code.splitlines(keepends=True))
    if closed:
        text += prefix + marker + "\n"
    file = tmp_path / "python.md"
    file.write_text(text)
    return file, text, code


def test_fence_scan_python_body_is_retained(fence_scan_python_case):
    # Arrange
    _, text, code = fence_scan_python_case
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == [(0, 2, code)]


def test_fence_scan_python_findings_have_document_lines(fence_scan_python_case):
    # Arrange
    file, _, _ = fence_scan_python_case
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", 3)]


@pytest.fixture(params=[(marker, tag, indent) for marker, tag in [("````", "text"), ("~~~", "bash"), ("```", "text"), ("~~~", "")] for indent in [0, 2]])
def fence_scan_foreign_case(request, tmp_path):
    marker, tag, indent = request.param
    prefix = " " * indent
    text = prefix + marker + tag + "\n" + prefix + "```python\n" + prefix + "def broken(\n" + prefix + "```\n" + prefix + marker + "\n"
    file = tmp_path / "foreign.md"
    file.write_text(text)
    return file, text


def test_fence_scan_foreign_body_has_no_python_units(fence_scan_foreign_case):
    # Arrange
    _, text = fence_scan_foreign_case
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == []


def test_fence_scan_foreign_body_is_not_parsed_as_python(fence_scan_foreign_case):
    # Arrange
    file, _ = fence_scan_foreign_case
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert issues == []


@pytest.fixture(params=[(marker, indent) for marker in ["```", "````", "~~~", "~~~~"] for indent in [0, 2]])
def fence_scan_invalid_eof_case(request, tmp_path):
    marker, indent = request.param
    prefix = " " * indent
    file = tmp_path / "invalid-eof.md"
    file.write_text(prefix + marker + "py\n" + prefix + "def broken(\n")
    return str(file)


def test_fence_scan_eof_exposes_optin_python_syntax_error(fence_scan_invalid_eof_case):
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError, match="::block-0:1:"):
        lint_file(fence_scan_invalid_eof_case, raise_input_errors=True)


def test_fence_scan_eof_keeps_default_syntax_error_policy(fence_scan_invalid_eof_case):
    # Arrange
    # Act
    issues = lint_file(fence_scan_invalid_eof_case)
    # Assert
    assert issues == []
