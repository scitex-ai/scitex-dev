"""SK-601 scope: user-facing skill examples write `import scitex as stx`;
only package source shown in a skill (a ```python block headed by a `src/`
path) must not."""

from __future__ import annotations

from scitex_dev._cli.audit._skills._checks import _check_import_alias

FENCE = "```"


def _ids(tmp_path, text):
    leaf = tmp_path / "01_usage.md"
    leaf.write_text(text, encoding="utf-8")
    out = []
    _check_import_alias(leaf, out)
    return [v.rule for v in out]


def test_user_facing_example_with_stx_alias_is_allowed(tmp_path):
    # Arrange
    text = f"# Usage\n\n{FENCE}python\nimport scitex as stx\nstx.io.save(x, 'a.csv')\n{FENCE}\n"
    # Act
    found = _ids(tmp_path, text)
    # Assert
    assert found == []


def test_package_source_block_with_stx_alias_is_reported(tmp_path):
    # Arrange
    text = f"{FENCE}python\n# src/scitex_foo/_core.py\nimport scitex as stx\n{FENCE}\n"
    # Act
    found = _ids(tmp_path, text)
    # Assert
    assert found == ["SK-601"]


def test_package_source_block_importing_a_leaf_is_allowed(tmp_path):
    # Arrange
    text = (
        f"{FENCE}python\n# src/scitex_foo/_core.py\nimport scitex_io as sio\n{FENCE}\n"
    )
    # Act
    found = _ids(tmp_path, text)
    # Assert
    assert found == []
