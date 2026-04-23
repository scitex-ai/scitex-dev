"""Regression tests for scitex-dev#143 — get_ecosystem_versions flat helper."""

from __future__ import annotations

from scitex_dev import get_ecosystem_versions


class TestGetEcosystemVersions:
    def test_returns_flat_dict(self):
        v = get_ecosystem_versions(["scitex"])
        assert isinstance(v, dict)
        # Key must be package name (NOT the detailed dict)
        assert "scitex" in v
        # Value must be a string version (or None if not installed)
        assert isinstance(v["scitex"], (str, type(None)))

    def test_multiple_packages(self):
        v = get_ecosystem_versions(["scitex", "figrecipe"])
        assert set(v.keys()) == {"scitex", "figrecipe"}
        for pkg, ver in v.items():
            assert isinstance(ver, (str, type(None)))

    def test_unknown_package_returns_none(self):
        v = get_ecosystem_versions(["totally-nonexistent-pkg"])
        # Either absent entirely or mapped to None — both acceptable
        assert v.get("totally-nonexistent-pkg") is None

    def test_format_is_flat_not_nested(self):
        """#143 spec: `{pkg: version_str}` — NOT the detailed multi-key dict
        that `list_versions(...)` returns."""
        v = get_ecosystem_versions(["scitex"])
        ver = v["scitex"]
        # If the helper accidentally returned the detailed dict, ver would
        # be a dict with "local"/"git"/"remote"/"status" keys.
        assert not isinstance(ver, dict)


# EOF
