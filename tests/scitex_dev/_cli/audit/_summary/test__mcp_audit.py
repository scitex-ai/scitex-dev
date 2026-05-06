#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary._mcp_audit — MCP-side helpers."""

from __future__ import annotations


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
        assert _import_name("scitex-cloud") == "scitex_cloud"

    def test_short_name(self):
        assert _short_name("scitex-cloud") == "cloud"

    def test_short_name_umbrella(self):
        assert _short_name("scitex") == "scitex"

    def test_short_name_compound_uses_underscore(self):
        # Compound names must produce a valid Python identifier suffix
        # so they can serve as both tool prefix and bridge-file basename.
        assert _short_name("scitex-orochi-mcp") == "orochi_mcp"
        assert _short_name("scitex-cloud-mcp") == "cloud_mcp"


class TestSkipNonStandalone:
    def test_umbrella_skipped(self):
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex") is True

    def test_mcp_server_packages_skipped(self):
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-cloud-mcp") is True
        assert _should_skip("scitex-orochi-server") is True

    def test_normal_package_not_skipped(self):
        from scitex_dev._cli.audit._summary._mcp_audit import _should_skip

        assert _should_skip("scitex-cloud") is False
        assert _should_skip("scitex-stats") is False

    def test_audit_one_returns_skip_status(self):
        from scitex_dev._cli.audit._summary._mcp_audit import _audit_one_mcp

        status, violations = _audit_one_mcp("scitex")
        assert status == "skip-not-standalone"
        assert violations == []


class TestToolNamingOK:
    def test_canonical_verb_noun(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-cloud", ["cloud_repo_clone"], out)
        assert out == []

    def test_bare_verb_with_object_in_params(self):
        # `io_save` — bare verb is fine; save takes the object via a param.
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_save"], out)
        assert out == []

    def test_bare_verb_audio_speak(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-audio", ["audio_speak"], out)
        assert out == []


class TestToolNamingFlagged:
    def test_double_prefix(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-dev", ["dev_dev_bulk_rename"], out)
        rules = [v.rule for v in out]
        assert "§1" in rules

    def test_synonym_ls(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_ls_files"], out)
        assert any(v.rule == "§2" and "synonym" in v.message for v in out)

    def test_double_underscore_typo(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io__save"], out)
        # Either §2 typo or naming violation — message should mention `__`
        assert any("__" in v.message for v in out)

    def test_bare_needs_noun(self):
        # `cloud_list` — bare `list` needs a noun.
        out: list[Violation] = []
        _check_tool_naming("scitex-cloud", ["cloud_list"], out)
        assert any(v.rule == "§2" and "needs" in v.message for v in out)

    def test_uppercase_rejected(self):
        out: list[Violation] = []
        _check_tool_naming("scitex-io", ["io_SaveFile"], out)
        assert any("snake_case" in v.message for v in out)


class TestSkillsPair:
    def test_present(self):
        out: list[Violation] = []
        _check_skills_pair(
            "scitex-cloud", {"cloud_skills_list", "cloud_skills_get"}, out
        )
        assert out == []

    def test_present_under_convention_a_bare(self):
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"skills_list", "skills_get"}, out)
        assert out == []

    def test_missing_both(self):
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"repo_clone"}, out)
        assert len(out) == 2
        assert all(v.rule == "§5" for v in out)

    def test_missing_one(self):
        out: list[Violation] = []
        _check_skills_pair("scitex-cloud", {"cloud_skills_list"}, out)
        assert len(out) == 1
        assert "skills_get" in out[0].message


class TestBridgePattern:
    def test_no_bridge_no_violation(self, monkeypatch):
        from scitex_dev._cli.audit._summary import _mcp_audit as mod

        monkeypatch.setattr(mod, "_read_bridge_source", lambda pkg: None)
        out: list[Violation] = []
        _check_bridge_pattern("scitex-bogus", out)
        assert out == []

    def test_safe_mount_bridge_clean(self, monkeypatch):
        from scitex_dev._cli.audit._summary import _mcp_audit as mod

        src = (
            "from ._compat import safe_mount\n"
            "def register_cloud_tools(mcp):\n"
            "    safe_mount(mcp, sub_mcp, namespace='cloud')\n"
        )
        monkeypatch.setattr(mod, "_read_bridge_source", lambda pkg: src)
        out: list[Violation] = []
        _check_bridge_pattern("scitex-cloud", out)
        assert out == []

    def test_hand_wrap_flagged(self, monkeypatch):
        from scitex_dev._cli.audit._summary import _mcp_audit as mod

        src = "@mcp.tool()\nasync def audio_speak(text: str) -> str:\n    pass\n"
        monkeypatch.setattr(mod, "_read_bridge_source", lambda pkg: src)
        # Also mock `_resolve_mcp_server` — the bridge-pattern check
        # consults it to decide whether hand-wrap is the only available
        # option (when the standalone has no `_mcp_server.mcp`, hand-wrap
        # is forgiven). Force a non-None to keep the §1 enforcement
        # active regardless of which peer standalones happen to be
        # installed in the test env (locally vs CI differ).
        monkeypatch.setattr(mod, "_resolve_mcp_server", lambda pkg: object())
        out: list[Violation] = []
        _check_bridge_pattern("scitex-audio", out)
        assert len(out) == 1
        assert out[0].rule == "§1"
        assert "hand-wrap" in out[0].message

    def test_direct_mount_flagged(self, monkeypatch):
        """`mcp.mount(...)` without `safe_mount` is now drift (§1)."""
        from scitex_dev._cli.audit._summary import _mcp_audit as mod

        src = (
            "def register_io_tools(mcp):\n"
            "    from scitex_io._mcp.server import mcp as io_mcp\n"
            "    mcp.mount(io_mcp)\n"
        )
        monkeypatch.setattr(mod, "_read_bridge_source", lambda pkg: src)
        out: list[Violation] = []
        _check_bridge_pattern("scitex-io", out)
        assert len(out) == 1
        assert out[0].rule == "§1"
        assert "direct `mcp.mount" in out[0].message
        assert "safe_mount" in out[0].message
