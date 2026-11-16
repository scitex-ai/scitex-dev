"""Read real installed metadata without executing provider code."""

import json
import sys
import pytest
from scitex_dev.package_hierarchy import list_package_hierarchies, validate_package_hierarchy
from ._fixtures import _catalog, _provider, import_path

def test_installed_metadata_reads_json_without_importing_provider(tmp_path, import_path):
    # Arrange
    _provider(tmp_path)
    import_path(tmp_path)
    # Act
    catalogs = list_package_hierarchies(path=[tmp_path])
    # Assert
    assert (catalogs, "inert_hierarchy_fixture" in sys.modules) == ((validate_package_hierarchy(_catalog()),), False)


def test_duplicate_provider_fails_instead_of_selecting_first(tmp_path, import_path):
    # Arrange
    _provider(tmp_path)
    _provider(tmp_path, owner="other-example")
    import_path(tmp_path)
    # Act
    # Assert
    with pytest.raises(ValueError, match="duplicate hierarchy provider"):
        list_package_hierarchies(path=[tmp_path])


def _break_resource(resource, tmp_path, case):
    if case == "missing":
        resource.unlink()
    elif case == "symlink":
        resource.unlink()
        target = tmp_path / "outside.json"
        target.write_text(json.dumps(_catalog()))
        resource.symlink_to(target)
    elif case == "duplicate-json":
        resource.write_text('{"root":"example","root":"other"}')
    elif case == "oversize":
        resource.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    else:
        data = _catalog()
        data["root"] = "apps"
        resource.write_text(json.dumps(data))


@pytest.mark.parametrize("case", ["missing", "symlink", "duplicate-json", "oversize", "root-mismatch"])
def test_broken_declared_resource_fails(tmp_path, import_path, case):
    # Arrange
    package = _provider(tmp_path)
    resource = package / "_package_hierarchy.json"
    import_path(tmp_path)
    _break_resource(resource, tmp_path, case)
    # Act
    # Assert
    with pytest.raises((ValueError, OSError)):
        list_package_hierarchies(path=[tmp_path])


def test_no_provider_is_an_empty_catalog_set(tmp_path):
    # Arrange
    location = tmp_path
    # Act
    catalogs = list_package_hierarchies(path=[location])
    # Assert
    assert catalogs == ()


@pytest.mark.parametrize("target", ["os.path", "example:load", "../escape"])
def test_executable_or_nested_target_is_rejected(tmp_path, target):
    # Arrange
    info = tmp_path / "invalid-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: invalid\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(f"[scitex_dev.hierarchy]\nexample = {target}\n")
    # Act
    # Assert
    with pytest.raises(ValueError, match="top-level package"):
        list_package_hierarchies(path=[tmp_path])
