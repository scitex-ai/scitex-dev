"""Regression tests for scitex-dev#143 — get_ecosystem_versions flat helper."""

from __future__ import annotations

from scitex_dev import get_ecosystem_versions


class TestGetEcosystemVersions:
    def test_returns_flat_dict_isinstance_v_dict(self):
        # Arrange
        # Act
        # Assert
        v = get_ecosystem_versions(["scitex"])
        assert isinstance(v, dict)
        # Key must be package name (NOT the detailed dict)
        # Value must be a string version (or None if not installed)

    def test_returns_flat_dict_scitex_in_v(self):
        # Arrange
        # Act
        # Assert
        v = get_ecosystem_versions(["scitex"])
        # Key must be package name (NOT the detailed dict)
        assert "scitex" in v
        # Value must be a string version (or None if not installed)

    def test_returns_flat_dict_isinstance_v_scitex_str_type_none(self):
        # Arrange
        # Act
        # Assert
        v = get_ecosystem_versions(["scitex"])
        # Key must be package name (NOT the detailed dict)
        # Value must be a string version (or None if not installed)
        assert isinstance(v["scitex"], (str, type(None)))

    def test_multiple_packages_return_entries_keyed_by_name(self):
        # Arrange
        # Act
        v = get_ecosystem_versions(["scitex", "figrecipe"])
        # Assert
        assert set(v.keys()) == {"scitex", "figrecipe"}

    def test_multiple_packages_values_are_strings_or_none(self):
        # Arrange
        # Act
        v = get_ecosystem_versions(["scitex", "figrecipe"])
        # Assert
        assert all(isinstance(ver, (str, type(None))) for ver in v.values())

    def test_unknown_package_returns_none(self):
        # Arrange
        # Act
        # Assert
        v = get_ecosystem_versions(["totally-nonexistent-pkg"])
        # Either absent entirely or mapped to None — both acceptable
        assert v.get("totally-nonexistent-pkg") is None

    def test_format_is_flat_not_nested(self):
        """#143 spec: `{pkg: version_str}` — NOT the detailed multi-key dict
        that `list_versions(...)` returns."""
        # Arrange
        # Act
        # Assert
        v = get_ecosystem_versions(["scitex"])
        ver = v["scitex"]
        # If the helper accidentally returned the detailed dict, ver would
        # be a dict with "local"/"git"/"remote"/"status" keys.
        assert not isinstance(ver, dict)


# EOF
