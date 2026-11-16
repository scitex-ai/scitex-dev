"""Validate stable navigation identities and index relationships."""

import copy
import pytest
from scitex_dev.package_hierarchy import validate_package_hierarchy
from ._fixtures import _catalog

def test_round_trip_and_numeric_order():
    # Arrange
    data = _catalog()
    data["nodes"].append({"id": "another", "label": "Another", "index": "1.10", "parent_id": "apps", "kind": "group"})
    data["nodes"].reverse()
    # Act
    result = validate_package_hierarchy(data)
    restored = validate_package_hierarchy(result.as_dict())
    # Assert
    assert (result == restored, [node.index for node in result.nodes]) == (True, ["0", "1", "1.2", "1.10"])


@pytest.mark.parametrize("field,value", [
    ("index", "01.2"), ("index", "1.0"), ("index", "1.2.3"),
    ("index", "2.2"), ("index", "1"), ("parent_id", "missing"),
    ("parent_id", "package:example-leaf"), ("kind", "root"),
    ("distribution", "Example_Leaf"), ("label", ""), ("id", "apps"),
])
def test_invalid_node_is_rejected(field, value):
    # Arrange
    data = _catalog()
    data["nodes"][2][field] = value
    # Act
    # Assert
    with pytest.raises(ValueError):
        validate_package_hierarchy(data)


def _break_catalog(data, change):
    if change == "boolean-version":
        data["schema_version"] = True
    elif change == "unknown-field":
        data["source_path"] = "/private/proposal.pdf"
    elif change == "duplicate-package":
        node = copy.copy(data["nodes"][2])
        node.update(id="duplicate", index="1.3")
        data["nodes"].append(node)
    elif change == "cycle":
        data["nodes"][1]["parent_id"] = "apps"
    else:
        data["nodes"][1]["kind"] = "root"


@pytest.mark.parametrize("change", ["boolean-version", "unknown-field", "duplicate-package", "cycle", "second-root"])
def test_invalid_catalog_is_rejected(change):
    # Arrange
    data = _catalog()
    _break_catalog(data, change)
    # Act
    # Assert
    with pytest.raises(ValueError):
        validate_package_hierarchy(data)


