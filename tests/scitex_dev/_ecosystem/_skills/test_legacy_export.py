"""Stage materialization preserves nested file paths from real installed providers."""

from scitex_dev._ecosystem._skills.legacy_export import export_unchecked


def test_linked_nested_export_paths_exist(tmp_path):
    # Arrange
    target = tmp_path / "stage"
    # Act
    exported = export_unchecked(target, package="scitex-dev", link=True)
    missing = [
        str(path) for paths in exported.values() for path in paths if not path.is_file()
    ]
    # Assert
    assert missing == []
