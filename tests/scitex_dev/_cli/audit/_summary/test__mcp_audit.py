#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary._mcp_audit — MCP-side helpers."""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._mcp_audit import (
    _check_bridge_pattern,
    _check_skills_pair,
    _check_tool_naming,
    _import_name,
    _short_name,
)


class TestNameDerivation:
    def test_import_name_replaces_hyphen(self):
        # Arrange
        # Act
        # Assert
        assert _import_name("scitex-cloud") == "scitex_cloud"

    def test_short_name_strips_scitex_prefix(self):
        # Arrange
        # Act
        # Assert
        assert _short_name("scitex-cloud") == "cloud"

    def test_short_name_keeps_umbrella_name_unchanged(self):
        # Arrange
        # Act
        # Assert
        assert _short_name("scitex") == "scitex"

    def test_short_name_compound_uses_underscore_short_name_scitex_orochi_mcp_orochi_mcp(
        self,
    ):
        # Compound names must produce a valid Python identifier suffix
        # so they can serve as both tool prefix and bridge-file basename.
        # Arrange
        # Act
        # Assert
        assert _short_name("scitex-orochi-mcp") == "orochi_mcp"

    def test_short_name_compound_uses_underscore_short_name_scitex_cloud_mcp_cloud_mcp(
        self,
    ):
        # Compound names must produce a valid Python identifier suffix
        # so they can serve as both tool prefix and bridge-file basename.
        # Arrange
        # Act
        # Assert
        assert _short_name("scitex-cloud-mcp") == "cloud_mcp"


class TestSkipNonStandalone:
    def test_umbrella_package_is_skipped(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex") is True

    def test_mcp_server_packages_skipped_should_skip_scitex_cloud_mcp_is_true(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-cloud-mcp") is True

    def test_mcp_server_packages_skipped_should_skip_scitex_orochi_server_is_true(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-orochi-server") is True

    def test_normal_package_not_skipped_should_skip_scitex_cloud_is_false(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-cloud") is False

    def test_normal_package_not_skipped_should_skip_scitex_stats_is_false(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-stats") is False

    def test_audit_one_returns_skip_status_status_skip_not_standalone(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _audit_one_mcp

        status, violations = _audit_one_mcp("scitex")
        assert status == "skip-not-standalone"

    def test_audit_one_returns_skip_status_violations(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev._cli.audit._summary._mcp_audit import _audit_one_mcp

        status, violations = _audit_one_mcp("scitex")
        assert violations == []


class TestToolNamingOK:
    def test_canonical_verb_noun_passes(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-cloud", ["cloud_repo_clone"], out)
        assert out == []

    def test_bare_verb_with_object_in_params(self):
        # `io_save` — bare verb is fine; save takes the object via a param.
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_save"], out)
        assert out == []

    def test_bare_verb_audio_speak_is_accepted(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-audio", ["audio_speak"], out)
        assert out == []


class TestToolNamingFlagged:
    def test_double_prefix_in_tool_name_is_flagged(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-dev", ["dev_dev_bulk_rename"], out)
        rules = [v.rule for v in out]
        assert "§1" in rules

    def test_ls_synonym_for_list_is_flagged(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_ls_files"], out)
        assert any(v.rule == "§2" and "synonym" in v.message for v in out)

    def test_double_underscore_typo_is_flagged(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io__save"], out)
        # Either §2 typo or naming violation — message should mention `__`
        assert any("__" in v.message for v in out)

    def test_bare_verb_list_needs_noun_object(self):
        # `cloud_list` — bare `list` needs a noun.
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-cloud", ["cloud_list"], out)
        assert any(v.rule == "§2" and "needs" in v.message for v in out)

    def test_uppercase_tool_name_rejected_as_non_snake(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_SaveFile"], out)
        assert any("snake_case" in v.message for v in out)


class TestSkillsPair:
    def test_both_skills_present_yields_no_violations(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair(
            "scitex-cloud", {"cloud_skills_list", "cloud_skills_get"}, out
        )
        assert out == []

    def test_present_under_convention_a_bare(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"skills_list", "skills_get"}, out)
        assert out == []

    def test_missing_both_skills_emits_two_violations_len_out_2(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"repo_clone"}, out)
        assert len(out) == 2

    def test_missing_both_skills_emits_two_violations_all_v_rule_5_for_v_in_out(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"repo_clone"}, out)
        assert all(v.rule == "§5" for v in out)

    def test_missing_one_skill_emits_single_violation_len_out_1(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"cloud_skills_list"}, out)
        assert len(out) == 1

    def test_missing_one_skill_emits_single_violation_skills_get_in_out_0_message(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"cloud_skills_list"}, out)
        assert "skills_get" in out[0].message


class TestBridgePattern:
    def test_no_bridge_no_violation(self):
        # Arrange
        # Act
        # Assert
        out: list[Violation] = []
        _check_bridge_pattern("scitex-bogus", out, read_bridge_source=lambda pkg: None)
        assert out == []

    def test_safe_mount_bridge_clean(self):
        # Arrange
        # Act
        # Assert
        src = (
            "from ._compat import safe_mount\n"
            "def register_cloud_tools(mcp):\n"
            "    safe_mount(mcp, sub_mcp, namespace='cloud')\n"
        )
        out: list[Violation] = []
        _check_bridge_pattern("scitex-cloud", out, read_bridge_source=lambda pkg: src)
        assert out == []

    def test_hand_wrap_flagged_len_out_1(self):
        # Arrange
        # Act
        # Assert
        src = "@mcp.tool()\nasync def audio_speak(text: str) -> str:\n    pass\n"
        # `resolve_mcp_server` injection: force a non-None so §1 enforcement
        # is active regardless of which peer standalones are installed.
        out: list[Violation] = []
        _check_bridge_pattern(
            "scitex-audio",
            out,
            read_bridge_source=lambda pkg: src,
            resolve_mcp_server=lambda pkg: object(),
        )
        assert len(out) == 1

    def test_hand_wrap_flagged_out_0_rule_1u_for_a_non_owner(self):
        """`scitex-audio` does not ship the bridge, so it gets the §1u sibling."""
        # Arrange
        src = "@mcp.tool()\nasync def audio_speak(text: str) -> str:\n    pass\n"
        # `resolve_mcp_server` injection: force a non-None so §1 enforcement
        # is active regardless of which peer standalones are installed.
        out: list[Violation] = []
        # Act
        _check_bridge_pattern(
            "scitex-audio",
            out,
            read_bridge_source=lambda pkg: src,
            resolve_mcp_server=lambda pkg: object(),
        )
        # Assert
        assert out[0].rule == "§1u"

    def test_hand_wrap_flagged_hand_wrap_in_out_0_message(self):
        # Arrange
        # Act
        # Assert
        src = "@mcp.tool()\nasync def audio_speak(text: str) -> str:\n    pass\n"
        # `resolve_mcp_server` injection: force a non-None so §1 enforcement
        # is active regardless of which peer standalones are installed.
        out: list[Violation] = []
        _check_bridge_pattern(
            "scitex-audio",
            out,
            read_bridge_source=lambda pkg: src,
            resolve_mcp_server=lambda pkg: object(),
        )
        assert "hand-wrap" in out[0].message

    def test_direct_mount_flagged_len_out_1(self):
        """`mcp.mount(...)` without `safe_mount` is now drift (§1)."""
        # Arrange
        # Act
        # Assert
        src = (
            "def register_io_tools(mcp):\n"
            "    from scitex_io._mcp.server import mcp as io_mcp\n"
            "    mcp.mount(io_mcp)\n"
        )
        out: list[Violation] = []
        _check_bridge_pattern("scitex-io", out, read_bridge_source=lambda pkg: src)
        assert len(out) == 1

    def test_direct_mount_flagged_out_0_rule_1u_for_a_non_owner(self):
        """The io bridge ships in the umbrella, so io's run gets §1u, not §1."""
        # Arrange
        src = (
            "def register_io_tools(mcp):\n"
            "    from scitex_io._mcp.server import mcp as io_mcp\n"
            "    mcp.mount(io_mcp)\n"
        )
        out: list[Violation] = []
        # Act
        _check_bridge_pattern("scitex-io", out, read_bridge_source=lambda pkg: src)
        # Assert
        assert out[0].rule == "§1u"

    def test_direct_mount_flagged_direct_mcp_mount_in_out_0_message(self):
        """`mcp.mount(...)` without `safe_mount` is now drift (§1)."""
        # Arrange
        # Act
        # Assert
        src = (
            "def register_io_tools(mcp):\n"
            "    from scitex_io._mcp.server import mcp as io_mcp\n"
            "    mcp.mount(io_mcp)\n"
        )
        out: list[Violation] = []
        _check_bridge_pattern("scitex-io", out, read_bridge_source=lambda pkg: src)
        assert "direct `mcp.mount" in out[0].message

    def test_direct_mount_flagged_safe_mount_in_out_0_message(self):
        """`mcp.mount(...)` without `safe_mount` is now drift (§1)."""
        # Arrange
        # Act
        # Assert
        src = (
            "def register_io_tools(mcp):\n"
            "    from scitex_io._mcp.server import mcp as io_mcp\n"
            "    mcp.mount(io_mcp)\n"
        )
        out: list[Violation] = []
        _check_bridge_pattern("scitex-io", out, read_bridge_source=lambda pkg: src)
        assert "safe_mount" in out[0].message


class TestListTools:
    """`_list_tools` must work on FastMCP 2.x (get_tools dict) and 3.x (list).

    Regression guard: it previously called `mcp.list_tools()` directly, which
    raised `AttributeError` on FastMCP 2.x. It now routes through the
    `get_tools_sync` version-bridge shim.
    """

    @staticmethod
    def _server():
        FastMCP = pytest.importorskip("fastmcp").FastMCP
        mcp = FastMCP("test-server")

        @mcp.tool()
        def cloud_repo_clone(url: str) -> str:
            """Clone a repo."""
            return url

        return mcp

    def test_list_tools_on_fastmcp_server_returns_a_list(self):
        # Arrange
        from scitex_dev._cli.audit._summary._mcp_audit import _list_tools

        # Act
        tools = _list_tools(self._server())
        # Assert
        assert isinstance(tools, list)

    def test_list_tools_includes_registered_tool_by_name(self):
        # Arrange
        from scitex_dev._cli.audit._summary._mcp_audit import _list_tools

        # Act
        names = [getattr(t, "name", "") for t in _list_tools(self._server())]
        # Assert
        assert "cloud_repo_clone" in names


class TestReadBridgeSourceNamespacePackage:
    """Regression for the namespace-package `__file__=None` TypeError that
    used to crash `test_audit_all_clean` ecosystem-wide and force admin-merge
    on every scitex-* PR.

    Previously: `Path(getattr(bridge_pkg, "__file__", "")).parent`. When
    the attribute *exists* and is None (namespace package), `getattr`'s
    default `""` does NOT fire, so `Path(None)` raised TypeError instead
    of "no concrete bridge file". No-mock regression — uses a real
    SimpleNamespace as the injected bridge package.
    """

    def test_namespace_pkg_with_none_file_returns_none_not_raises(self):
        # Arrange
        import types
        from scitex_dev._cli.audit._summary._mcp_audit import _read_bridge_source

        fake_namespace_pkg = types.SimpleNamespace(__file__=None)

        # Act
        result = _read_bridge_source(
            "scitex-anything", import_bridge_pkg=lambda: fake_namespace_pkg
        )

        # Assert
        assert result is None  # MUST NOT raise TypeError

    def test_missing_file_attr_also_returns_none(self):
        # Arrange — also defensively covers the "attribute absent" case
        # (which the original getattr default would have handled).
        import types
        from scitex_dev._cli.audit._summary._mcp_audit import _read_bridge_source

        fake_pkg_no_file = types.SimpleNamespace()  # no __file__ attr at all

        # Act
        result = _read_bridge_source(
            "scitex-anything", import_bridge_pkg=lambda: fake_pkg_no_file
        )

        # Assert
        assert result is None

    def test_import_failure_returns_none(self):
        # Arrange — the existing "bridge pkg can't be imported" path
        # still returns None (not crash) when the importer raises.
        from scitex_dev._cli.audit._summary._mcp_audit import _read_bridge_source

        def _raises_on_import():
            raise ImportError("synthetic — bridge unavailable")

        # Act
        result = _read_bridge_source(
            "scitex-anything", import_bridge_pkg=_raises_on_import
        )

        # Assert
        assert result is None

    def test_check_bridge_pattern_swallows_namespace_pkg_via_default_reader(self):
        # Arrange — end-to-end: with the *real* default reader, when the
        # umbrella resolves as a namespace pkg the orchestrator must not
        # crash. We can't easily install a namespace umbrella in CI, but
        # we can prove the contract: `_check_bridge_pattern` reads via
        # `_read_bridge_source` and treats None as "no bridge → no violation".
        import types
        from scitex_dev._cli.audit._summary._audit import Violation
        from scitex_dev._cli.audit._summary._mcp_audit import (
            _check_bridge_pattern,
            _read_bridge_source,
        )

        fake_namespace_pkg = types.SimpleNamespace(__file__=None)

        def _reader(package: str):
            return _read_bridge_source(
                package, import_bridge_pkg=lambda: fake_namespace_pkg
            )

        out: list[Violation] = []

        # Act — must not raise TypeError
        _check_bridge_pattern(
            "scitex-anything",
            out,
            read_bridge_source=_reader,
            resolve_mcp_server=lambda pkg: object(),
        )

        # Assert
        assert out == []
