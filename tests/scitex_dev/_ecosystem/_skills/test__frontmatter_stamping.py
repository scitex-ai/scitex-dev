"""Export metadata must never rewrite an instruction or example in the body."""

from __future__ import annotations

import pytest

from scitex_dev._ecosystem._skills._frontmatter import _stamp_frontmatter_field


@pytest.mark.parametrize("key", ["version", "exported_via"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_missing_header_field_preserves_code_and_prose_values(key, newline):
    # Arrange
    body = f"# Instructions{newline}```yaml{newline}{key}: 2{newline}```{newline}"
    header = f"---{newline}description: Keep --- literal text{newline}"
    content = header + f"---{newline}" + body
    expected = header + f"{key}: 1.2.3{newline}---{newline}" + body
    # Act
    result = _stamp_frontmatter_field(content, key, "1.2.3")
    # Assert
    assert result == expected


@pytest.mark.parametrize("closing", ["---\n", "---"])
def test_empty_header_receives_one_field_without_a_second_header(closing):
    # Arrange
    content = "---\n" + closing
    expected = "---\nversion: 1.2.3\n" + closing
    # Act
    result = _stamp_frontmatter_field(content, "version", "1.2.3")
    # Assert
    assert result == expected


def test_legacy_body_field_is_preserved_after_prepending_metadata():
    # Arrange
    content = "# Example\n```yaml\nversion: 2\n```\n"
    expected = "---\nversion: 1.2.3\n---\n\n" + content
    # Act
    result = _stamp_frontmatter_field(content, "version", "1.2.3")
    # Assert
    assert result == expected


def test_blank_header_value_does_not_consume_the_following_field():
    # Arrange
    content = "---\nversion:   \nexported_via: source\n---\nversion: 2\n"
    expected = "---\nversion:   1.2.3\nexported_via: source\n---\nversion: 2\n"
    # Act
    result = _stamp_frontmatter_field(content, "version", "1.2.3")
    # Assert
    assert result == expected


def test_replacement_value_is_literal_not_a_regular_expression_template():
    # Arrange
    content = "---\nexported_via: old\n---\n# Instructions\n"
    value = r"C:\drafts\one"
    expected = f"---\nexported_via: {value}\n---\n# Instructions\n"
    # Act
    result = _stamp_frontmatter_field(content, "exported_via", value)
    # Assert
    assert result == expected


def test_field_names_with_regex_punctuation_do_not_match_another_key():
    # Arrange
    content = "---\nreleaseXversion: preserve\n---\n# Body\n"
    expected = "---\nreleaseXversion: preserve\nrelease.version: 1.2.3\n---\n# Body\n"
    # Act
    result = _stamp_frontmatter_field(content, "release.version", "1.2.3")
    # Assert
    assert result == expected
