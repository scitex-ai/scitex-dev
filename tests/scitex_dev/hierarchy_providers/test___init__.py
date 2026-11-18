"""Validate actual declaration metadata without importing a provider or SDK."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scitex_dev
from scitex_dev.hierarchy_providers import list_hierarchy_providers

from ._fixtures import distribution


def test_real_catalog_preserves_owner_version_summary_and_target(tmp_path):
    # Arrange
    distribution(tmp_path, owner="Owned_Example")
    # Act
    rows = list_hierarchy_providers(path=[tmp_path])
    # Assert
    assert [(r.name, r.target, r.distribution, r.version, r.summary) for r in rows] == [
        (
            "owned-example",
            "missing_provider:get_nodes",
            "owned-example",
            "1.2.3",
            "Owned hierarchy",
        )
    ]


def test_discovery_does_not_execute_an_importable_provider_or_import_sdk(tmp_path):
    # Arrange
    marker = tmp_path / "provider-executed"
    (tmp_path / "owned_bomb.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('must not import')\n"
    )
    distribution(tmp_path, target="owned_bomb:get_nodes")
    code = "from scitex_dev.hierarchy_providers import list_hierarchy_providers;import json,sys;rows=list_hierarchy_providers(path=[sys.argv[1]]);print(json.dumps({'count':len(rows),'sdk_loaded':'scitex_sdk' in sys.modules}))"
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            (str(Path(scitex_dev.__file__).parent.parent), str(tmp_path))
        ),
    )
    # Act
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    # Assert
    assert (result.returncode, json.loads(result.stdout), marker.exists()) == (
        0,
        {"count": 1, "sdk_loaded": False},
        False,
    )


def test_explicit_empty_search_has_no_registry_or_environment_fallback():
    # Arrange
    locations = []
    # Act
    rows = list_hierarchy_providers(path=locations)
    # Assert
    assert rows == ()


def test_empty_metadata_directory_has_no_synthetic_provider(tmp_path):
    # Arrange
    locations = [tmp_path]
    # Act
    rows = list_hierarchy_providers(path=locations)
    # Assert
    assert rows == ()


def test_unrelated_provider_group_is_not_admitted(tmp_path):
    # Arrange
    distribution(tmp_path, group="scitex_dev.docs")
    # Act
    rows = list_hierarchy_providers(path=[tmp_path])
    # Assert
    assert rows == ()


def test_missing_version_remains_unknown(tmp_path):
    # Arrange
    distribution(tmp_path, version=None)
    # Act
    rows = list_hierarchy_providers(path=[tmp_path])
    # Assert
    assert rows[0].version is None


def test_package_filter_uses_canonical_identity(tmp_path):
    # Arrange
    distribution(tmp_path, owner="owned-example")
    distribution(tmp_path, owner="other-example", slot="two")
    # Act
    rows = list_hierarchy_providers(package="Owned_Example", path=[tmp_path])
    # Assert
    assert [r.distribution for r in rows] == ["owned-example"]


def test_absent_owner_is_not_invented(tmp_path):
    # Arrange
    distribution(tmp_path)
    # Act
    rows = list_hierarchy_providers(package="not-installed", path=[tmp_path])
    # Assert
    assert rows == ()


def test_catalog_order_is_independent_of_search_order(tmp_path):
    # Arrange
    first, second = tmp_path / "first", tmp_path / "second"
    distribution(first, owner="owned-z")
    distribution(second, owner="owned-a")
    # Act
    orders = [
        [r.name for r in list_hierarchy_providers(path=paths)]
        for paths in [(first, second), (second, first)]
    ]
    # Assert
    assert orders == [["owned-a", "owned-z"], ["owned-a", "owned-z"]]


@pytest.mark.parametrize(
    "target",
    [
        "module_only",
        "module:",
        "module:get_nodes [extra]",
        "../module:get",
        "module:get-nodes",
        "file:///tmp/provider.py:get",
        "module:get()",
    ],
)
def test_malformed_target_declarations_are_refused(tmp_path, target):
    # Arrange
    distribution(tmp_path, target=target)
    # Act
    # Assert
    with pytest.raises(ValueError, match="needs module:attribute"):
        list_hierarchy_providers(path=[tmp_path])


@pytest.mark.parametrize("name", ["alias", "Owned-Example", "owned_example"])
def test_declaration_name_must_match_canonical_owner(tmp_path, name):
    # Arrange
    distribution(tmp_path, name=name)
    # Act
    # Assert
    with pytest.raises(ValueError, match="name must equal its canonical owner"):
        list_hierarchy_providers(path=[tmp_path])


def test_even_identical_duplicate_ownership_claims_are_refused(tmp_path):
    # Arrange
    distribution(tmp_path)
    distribution(tmp_path, slot="two")
    # Act
    # Assert
    with pytest.raises(ValueError, match="duplicate hierarchy provider: owned-example"):
        list_hierarchy_providers(path=[tmp_path])


def test_package_filter_does_not_hide_invalid_other_declarations(tmp_path):
    # Arrange
    distribution(tmp_path)
    distribution(tmp_path, owner="other-owner", name="foreign-alias", slot="two")
    # Act
    # Assert
    with pytest.raises(ValueError, match="canonical owner: other-owner"):
        list_hierarchy_providers(package="owned-example", path=[tmp_path])


def test_invalid_package_identity_is_refused(tmp_path):
    # Arrange
    location = tmp_path
    # Act
    # Assert
    with pytest.raises(ValueError, match="invalid distribution name"):
        list_hierarchy_providers(package="../owner", path=[location])


def test_root_facade_exposes_the_same_metadata_reader():
    # Arrange
    expected = list_hierarchy_providers
    # Act
    actual = scitex_dev.list_hierarchy_providers
    # Assert
    assert actual is expected
