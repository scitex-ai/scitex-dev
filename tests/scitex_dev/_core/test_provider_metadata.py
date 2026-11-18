"""Keep physical metadata identity separate from genuine duplicate declarations."""

import sys
from importlib import metadata

import pytest

from scitex_dev._core.provider_metadata import read_provider_metadata
from scitex_dev.doc_providers import list_doc_providers
from scitex_dev.hierarchy_providers import list_hierarchy_providers


def _distribution(root, *, slot="one", group="scitex_dev.hierarchy", duplicate=False):
    info = root / f"owned_{slot}-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Name: owned-example\nVersion: 1.0\n")
    entry = "owned-example = unimportable_provider:get_nodes\n"
    (info / "entry_points.txt").write_text(
        f"[{group}]\n" + entry * (2 if duplicate else 1)
    )
    return info


def test_repeating_one_directory_does_not_repeat_a_physical_declaration(tmp_path):
    # Arrange
    _distribution(tmp_path)
    # Act
    rows = read_provider_metadata("scitex_dev.hierarchy", path=[tmp_path, tmp_path])
    # Assert
    assert [(r.name, r.distribution, r.target) for r in rows] == [
        ("owned-example", "owned-example", "unimportable_provider:get_nodes")
    ]


def test_hierarchy_discovery_does_not_invent_a_conflict_from_repeated_paths(tmp_path):
    # Arrange
    _distribution(tmp_path)
    # Act
    rows = list_hierarchy_providers(path=[tmp_path, tmp_path])
    # Assert
    assert [r.distribution for r in rows] == ["owned-example"]


def test_docs_discovery_uses_the_same_physical_identity_rule(tmp_path):
    # Arrange
    _distribution(tmp_path, group="scitex_dev.docs")
    # Act
    rows = list_doc_providers(path=[tmp_path, tmp_path])
    # Assert
    assert [r.distribution for r in rows] == ["owned-example"]


def test_directory_aliases_share_one_physical_metadata_origin(tmp_path):
    # Arrange
    site = tmp_path / "site"
    _distribution(site)
    alias = tmp_path / "alias"
    alias.symlink_to(site, target_is_directory=True)
    # Act
    rows = list_hierarchy_providers(path=[site, alias])
    # Assert
    assert len(rows) == 1


def test_two_actual_installations_still_produce_two_metadata_claims(tmp_path):
    # Arrange
    _distribution(tmp_path, slot="one")
    _distribution(tmp_path, slot="two")
    # Act
    rows = read_provider_metadata("scitex_dev.hierarchy", path=[tmp_path])
    # Assert
    assert len(rows) == 2


def test_hierarchy_still_rejects_identical_owners_from_distinct_origins(tmp_path):
    # Arrange
    _distribution(tmp_path, slot="one")
    _distribution(tmp_path, slot="two")
    # Act
    # Assert
    with pytest.raises(ValueError, match="duplicate hierarchy provider: owned-example"):
        list_hierarchy_providers(path=[tmp_path])


def test_two_declarations_inside_one_installation_are_not_deduplicated(tmp_path):
    # Arrange
    _distribution(tmp_path, duplicate=True)
    # Act
    # Assert
    with pytest.raises(ValueError, match="duplicate hierarchy provider: owned-example"):
        list_hierarchy_providers(path=[tmp_path, tmp_path])


def test_custom_distribution_semantics_are_not_collapsed_by_a_private_path(tmp_path):
    # Arrange
    info = _distribution(tmp_path)

    class CustomDistribution(metadata.PathDistribution):
        pass

    class Finder(metadata.DistributionFinder):
        @classmethod
        def find_distributions(cls, context=None):
            return (CustomDistribution(info), CustomDistribution(info))

    empty = tmp_path / "empty"
    empty.mkdir()
    sys.meta_path.insert(0, Finder)
    # Act
    try:
        rows = read_provider_metadata("scitex_dev.hierarchy", path=[empty])
    finally:
        sys.meta_path.remove(Finder)
    # Assert
    assert len(rows) == 2
