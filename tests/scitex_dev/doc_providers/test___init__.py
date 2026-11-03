"""Real dist-info discovery must not load consumer entry points."""

from pathlib import Path

from scitex_dev.doc_providers import list_doc_providers


def _distribution(root, name, target, *, group="scitex_dev.docs", version="1.2.3"):
    info = root / (name.replace("-", "_") + "-1.2.3.dist-info")
    info.mkdir()
    info.joinpath("METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: Owned example\n"
    )
    info.joinpath("entry_points.txt").write_text(f"[{group}]\nowned = {target}\n")


def test_real_metadata_returns_owned_rows_without_loading_target(tmp_path):
    # Arrange
    marker = tmp_path / "executed"
    target = tmp_path / "owned_unimportable_provider.py"
    target.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('must not execute')\n")
    _distribution(tmp_path, "owned-example", "owned_unimportable_provider")
    # Act
    rows = list_doc_providers(path=[tmp_path])
    observed = ([(row.name, row.target, row.distribution, row.version, row.summary)
                 for row in rows], marker.exists())
    # Assert
    assert observed == ([("owned", "owned_unimportable_provider", "owned-example",
                          "1.2.3", "Owned example")], False)


def test_duplicate_provider_names_are_preserved(tmp_path):
    # Arrange
    _distribution(tmp_path, "owned-z", "unimportable_z")
    _distribution(tmp_path, "owned-a", "unimportable_a")
    # Act
    rows = list_doc_providers(path=[tmp_path])
    # Assert
    assert [(row.name, row.distribution) for row in rows] == [
        ("owned", "owned-a"), ("owned", "owned-z")
    ]


def test_unrelated_entry_points_do_not_become_doc_providers(tmp_path):
    # Arrange
    _distribution(tmp_path, "owned-example", "unimportable", group="console_scripts")
    # Act
    rows = list_doc_providers(path=[tmp_path])
    # Assert
    assert rows == ()


def test_absent_metadata_is_empty_not_a_registry_fallback(tmp_path):
    # Arrange
    location = Path(tmp_path)
    # Act
    rows = list_doc_providers(path=[location])
    # Assert
    assert rows == ()
