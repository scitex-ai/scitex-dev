"""Real dist-info fixtures exercise inert, owner-scoped declaration discovery."""

import pytest

from scitex_dev._ecosystem._capability_providers import (
    read_capability_providers,
    select_capability_provider,
)


def _distribution(root, directory, *, owner="Owned.Example",
                  target="owned_provider:inventory", name="default",
                  group="scitex_dev.capabilities", version="1.2.3"):
    info = root / (directory + ".dist-info")
    info.mkdir(parents=True)
    metadata = "Metadata-Version: 2.1\nSummary: Owned fixture\n"
    if owner is not None:
        metadata += f"Name: {owner}\n"
    if version is not None:
        metadata += f"Version: {version}\n"
    (info / "METADATA").write_text(metadata)
    (info / "entry_points.txt").write_text(f"[{group}]\n{name} = {target}\n")
    return info


def test_actual_metadata_rows_are_inert_and_keep_declaration_identity(tmp_path):
    # Arrange
    marker = tmp_path / "executed"
    (tmp_path / "owned_provider.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('must not execute')\n"
    )
    _distribution(tmp_path, "owned_example-1.2.3")
    # Act
    rows = read_capability_providers(path=[tmp_path])
    # Assert
    assert ([(row.name, row.target, row.distribution, row.version, row.summary)
             for row in rows], marker.exists()) == (
        [("default", "owned_provider:inventory", "owned-example", "1.2.3",
          "Owned fixture")], False,
    )


def test_same_namespace_from_different_owners_is_preserved(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", owner="owned-a")
    _distribution(tmp_path, "two", owner="owned-b")
    # Act
    rows = read_capability_providers(path=[tmp_path])
    # Assert
    assert [(row.name, row.distribution) for row in rows] == [
        ("default", "owned-a"), ("default", "owned-b")
    ]


def test_selection_is_scoped_to_canonical_distribution_identity(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", owner="owned-a")
    _distribution(tmp_path, "two", owner="owned-b", target="other_provider:inventory")
    rows = read_capability_providers(path=[tmp_path])
    # Act
    selected = select_capability_provider(rows, distribution="Owned_B", name="default")
    # Assert
    assert (selected.distribution, selected.target) == (
        "owned-b", "other_provider:inventory"
    )


def test_selection_does_not_borrow_another_owners_provider(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", owner="owned-a")
    rows = read_capability_providers(path=[tmp_path])
    # Act
    def select():
        return select_capability_provider(rows, distribution="owned-b", name="default")
    # Assert
    with pytest.raises(LookupError, match="owned-b"):
        select()


def test_identical_duplicate_ownership_claims_remain_ambiguous(tmp_path):
    # Arrange
    _distribution(tmp_path, "one")
    _distribution(tmp_path, "two")
    rows = read_capability_providers(path=[tmp_path])
    # Act
    def select():
        return select_capability_provider(rows, distribution="owned-example", name="default")
    # Assert
    with pytest.raises(ValueError, match="ambiguous"):
        select()


@pytest.mark.parametrize("name", ["missing", "Default"])
def test_provider_names_are_exact_without_a_namespace_fallback(tmp_path, name):
    # Arrange
    _distribution(tmp_path, "one")
    rows = read_capability_providers(path=[tmp_path])
    # Act
    def select():
        return select_capability_provider(rows, distribution="owned-example", name=name)
    # Assert
    with pytest.raises(LookupError, match="no capability provider"):
        select()


@pytest.mark.parametrize("name", ["", " default", 42])
def test_invalid_selection_names_fail_loudly(name):
    # Arrange
    rows = ()
    # Act
    def select():
        return select_capability_provider(rows, distribution="owned-example", name=name)
    # Assert
    with pytest.raises(ValueError, match="provider name"):
        select()


@pytest.mark.parametrize(
    "target", ["owned_provider", "owned_provider:", ":inventory",
               "owned_provider:inventory:extra", "owned-provider:inventory"]
)
def test_malformed_factory_targets_are_not_certified(tmp_path, target):
    # Arrange
    _distribution(tmp_path, "one", target=target)
    # Act
    def read():
        return read_capability_providers(path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="module:attribute"):
        read()


def test_missing_owner_metadata_is_not_accepted(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", owner=None)
    # Act
    def read():
        return read_capability_providers(path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="Name"):
        read()


def test_unknown_version_remains_unknown(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", version=None)
    # Act
    rows = read_capability_providers(path=[tmp_path])
    # Assert
    assert rows[0].version is None


def test_unrelated_entry_points_are_not_capability_providers(tmp_path):
    # Arrange
    _distribution(tmp_path, "one", group="console_scripts")
    # Act
    rows = read_capability_providers(path=[tmp_path])
    # Assert
    assert rows == ()


def test_absent_metadata_has_no_registry_or_source_fallback(tmp_path):
    # Arrange
    # Act
    rows = read_capability_providers(path=[tmp_path])
    # Assert
    assert rows == ()


def test_non_metadata_rows_are_rejected():
    # Arrange
    rows = [{"name": "default", "distribution": "owned-example"}]
    # Act
    def select():
        return select_capability_provider(rows, distribution="owned-example", name="default")
    # Assert
    with pytest.raises(TypeError, match="ProviderMetadata"):
        select()
