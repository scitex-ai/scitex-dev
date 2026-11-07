"""Skill discovery must advertise YAML text, rather than its block marker."""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._ecosystem._skills._frontmatter import _parse_frontmatter
from scitex_dev._ecosystem._skills.skills import _collect_skills_from_dir


@pytest.mark.parametrize(
    "header,expected",
    [
        (
            "description: |\n  First line.\n  Second line.",
            "First line.\nSecond line.\n",
        ),
        ("description: >\n  First line.\n  Second line.", "First line. Second line.\n"),
        ("description: |-\n  No trailing newline.", "No trailing newline."),
        ('description: "Read: inspect the package"', "Read: inspect the package"),
        (
            'description: "Keep --- inside the description"',
            "Keep --- inside the description",
        ),
        ("description: 'An agent''s guide'", "An agent's guide"),
    ],
)
def test_yaml_descriptions_are_decoded(tmp_path: Path, header: str, expected: str):
    # Arrange
    path = tmp_path / "skill.md"
    path.write_text(f"---\n{header}\nversion: 1.2.3\n---\n# Body\n")
    # Act
    result = _parse_frontmatter(path)
    # Assert
    assert (result.get("description"), result.get("version")) == (expected, "1.2.3")


@pytest.mark.parametrize(
    "content",
    [
        "---\ndescription: [unclosed\n---\n# Body\n",
        "---\n- a list, not a metadata mapping\n---\n# Body\n",
        "---\ndescription: !!python/object/apply:builtins.str [must-not-construct]\n---\n# Body\n",
        "---\ndescription: true\n---\n# Body\n",
        "---not-frontmatter\ndescription: not metadata\n---\n# Body\n",
    ],
)
def test_invalid_or_nontext_metadata_is_not_advertised(tmp_path: Path, content: str):
    # Arrange
    path = tmp_path / "skill.md"
    path.write_text(content)
    # Act
    result = _parse_frontmatter(path)
    # Assert
    assert result == {}


def test_inventory_exposes_multiline_description_and_relative_identity(tmp_path: Path):
    # Arrange
    path = tmp_path / "nested" / "guide.md"
    path.parent.mkdir()
    path.write_text(
        "---\ndescription: |\n  [TOPIC] Storage\n  [DETAILS] Inspect safely.\n"
        "---\n# A different body title\n"
    )
    # Act
    rows = _collect_skills_from_dir(tmp_path, "1.2.3")
    # Assert
    assert [(r["name"], r["description"], r["version"]) for r in rows] == [
        ("nested/guide", "[TOPIC] Storage\n[DETAILS] Inspect safely.\n", "1.2.3")
    ]
