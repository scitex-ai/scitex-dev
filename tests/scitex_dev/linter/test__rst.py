"""reST directive options cannot consume a dedented field-list body."""

import pytest

from scitex_dev.linter._rst import _iter_python_blocks
from scitex_dev.linter.checker import lint_file


@pytest.fixture(params=[(directive, outer, field) for directive in ["code-block", "code", "sourcecode", "ipython"] for outer, field in [(0, 0), (4, 0), (4, 4)]])
def outside_field_body(request, tmp_path):
    directive, outer, field = request.param
    text = " " * outer + ".. " + directive + ":: python\n\n" + " " * field + ":note: Not directive content\n" + " " * (outer + 4) + "import requests\n" + " " * (outer + 4) + 'requests.get("https://owned.invalid")\n'
    file = tmp_path / "outside.rst"
    file.write_text(text)
    return file, text


def test_dedented_field_body_is_not_a_python_unit(outside_field_body):
    # Arrange
    _, text = outside_field_body
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == []


def test_dedented_field_body_cannot_produce_python_findings(outside_field_body):
    # Arrange
    file, _ = outside_field_body
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert issues == []


@pytest.fixture(params=[(directive, indent, options) for directive in ["code-block", "code", "sourcecode", "ipython"] for indent in [0, 4] for options in [False, True]])
def real_directive_body(request, tmp_path):
    directive, indent, options = request.param
    prefix = " " * indent
    option = prefix + "    :linenos:\n" if options else ""
    text = prefix + ".. " + directive + ":: python\n" + option + "\n" + prefix + "    import requests\n" + prefix + '    requests.get("https://owned.invalid")\n'
    file = tmp_path / "actual.rst"
    file.write_text(text)
    return file, 5 if options else 4


def test_indented_options_and_directive_body_keep_findings_and_lines(real_directive_body):
    # Arrange
    file, expected_line = real_directive_body
    # Act
    issues = lint_file(str(file), raise_input_errors=True)
    # Assert
    assert [(issue.rule.id, issue.line) for issue in issues] == [("STX-NET001", expected_line)]


@pytest.fixture(params=[(directive, indent, options) for directive in ["code-block", "code", "sourcecode", "ipython"] for indent in [0, 4] for options in [False, True]])
def rst_content_separator_case(request, tmp_path):
    directive, indent, options = request.param
    prefix = " " * indent
    option = prefix + "    :linenos:\n" if options else ""
    text = prefix + ".. " + directive + ":: python\n" + option + "\n" + prefix + "    :not_python:\n"
    file = tmp_path / "content.rst"
    file.write_text(text)
    return file, text, 4 if options else 3


def test_content_separator_retains_colon_prefixed_code(rst_content_separator_case):
    # Arrange
    _, text, start_line = rst_content_separator_case
    # Act
    blocks = list(_iter_python_blocks(text))
    # Assert
    assert blocks == [(0, start_line, ":not_python:\n")]


def test_content_separator_optin_does_not_hide_invalid_python(rst_content_separator_case):
    # Arrange
    file, _, _ = rst_content_separator_case
    # Act
    # Assert
    with pytest.raises(ValueError, match="::block-0:1:"):
        lint_file(str(file), raise_input_errors=True)


def test_content_separator_preserves_default_syntax_error_behavior(rst_content_separator_case):
    # Arrange
    file, _, _ = rst_content_separator_case
    # Act
    issues = lint_file(str(file))
    # Assert
    assert issues == []
