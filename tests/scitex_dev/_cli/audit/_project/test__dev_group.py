"""Static contributor-group expansion preserves requirements and refuses bad data."""

import pytest

from scitex_dev._cli.audit._project._dev_group import dev_group_requirements


def test_includes_normalize_names_and_preserve_requirement_occurrences():
    # Arrange
    metadata = {
        "dependency-groups": {
            "Dev": ["packaging>20", {"include-group": "Test_Tools"}],
            "test-tools": ["packaging<100", "scitex-logging"],
        }
    }
    # Act
    result = dev_group_requirements(metadata)
    # Assert
    assert [str(r) for r in result] == [
        "packaging>20",
        "packaging<100",
        "scitex-logging",
    ]


def test_unrelated_group_contents_are_not_evaluated():
    # Arrange
    metadata = {
        "dependency-groups": {"dev": ["packaging"], "future": [{"future-key": True}]}
    }
    # Act
    result = dev_group_requirements(metadata)
    # Assert
    assert [r.name for r in result] == ["packaging"]


@pytest.mark.parametrize("metadata", [{}, {"dependency-groups": {"docs": ["sphinx"]}}])
def test_no_dev_group_preserves_legacy_selection(metadata):
    # Arrange
    # Act
    result = dev_group_requirements(metadata)
    # Assert
    assert result is None


@pytest.mark.parametrize("count", [4097])
def test_expansion_limit_refuses_overlong_group(count):
    # Arrange
    metadata = {"dependency-groups": {"dev": ["packaging"] * count}}
    # Act
    # Assert
    with pytest.raises(ValueError, match="4096"):
        dev_group_requirements(metadata)


def test_expansion_depth_refuses_long_acyclic_chain():
    # Arrange
    groups = {"dev": [{"include-group": "g0"}]}
    groups.update({f"g{i}": [{"include-group": f"g{i + 1}"}] for i in range(33)})
    groups["g33"] = ["packaging"]
    # Act
    # Assert
    with pytest.raises(ValueError, match="depth"):
        dev_group_requirements({"dependency-groups": groups})


def test_group_table_requires_mapping():
    # Arrange
    metadata = {"dependency-groups": []}
    # Act
    # Assert
    with pytest.raises(TypeError, match="table"):
        dev_group_requirements(metadata)
