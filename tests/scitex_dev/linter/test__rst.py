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
