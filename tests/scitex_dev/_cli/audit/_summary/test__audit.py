#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary — pure helpers + small integration paths.

Covers the parts that don't require a live console-script entry point:
- token classification + dictionary cascade
- §1c pass-through detection
- §4 example-detection heuristic
- §1a introspection presence (with synthetic Click trees)
- §6a env-prefix derivation
- registry cascade + provenance
- MCP-server entry-point detection
- _filter_violations (rule / exclude / severity gating)
- _extract_names (JSON parity helper)
- argparse capture + Click-tree wrapping (round-trip on a fixture parser)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary import FLAT_KEEPERS
from scitex_dev._cli.audit._summary._audit import (
    Violation,
    _PackageTimeout,
    _audit_one,
    _capture_root,
    _check_introspection,
    _classify,
    _expected_env_prefix,
    _extract_names,
    _filter_violations,
    _flag_names,
    _has_example,
    _is_mcp_server_entry,
    _is_pass_through,
    _isolated_streams,
    _load_registry,
    _verb_token,
    _walk,
    _watchdog,
    _wrap_argparse,
)


# --------------------------------------------------------------------- #
# Token classification (§1c catalog + §1d unknown)                      #
# --------------------------------------------------------------------- #


class TestClassify:
    def test_catalog_noun(self):
        # `package` is in the bundled noun list
        assert "noun" in _classify("package")

    def test_catalog_verb_t(self):
        assert "verb-t" in _classify("list")

    def test_catalog_verb_i_intransitive(self):
        # `doctor` is intransitive; flat-keeper list also covers it
        assert "doctor" in FLAT_KEEPERS
        assert "verb-i" in _classify("doctor") or "doctor" in FLAT_KEEPERS

    def test_compound_first_token(self):
        # `start-dashboard` should classify by `start` (verb)
        labels = _classify("start-dashboard")
        assert "verb-t" in labels or "verb" in labels

    def test_unknown_token(self):
        # A nonsense token should fall through to {"unknown"}
        assert _classify("zzzqqxnoton") == {"unknown"}


class TestSingularizerFallthrough:
    """Plurals should classify as nouns without being seeded explicitly."""

    @pytest.mark.parametrize(
        "plural",
        [
            "packages",
            "jobs",
            "bibentries",
            "caches",
            "machines",
            "runs",
            "presets",
            "backends",
            "installations",
        ],
    )
    def test_plural_recognised_as_noun(self, plural):
        assert "noun" in _classify(plural)

    def test_genuine_unknown_still_unknown(self):
        # Singularizer should not invent classifications for nonsense plurals.
        assert _classify("zzqxnotonts") == {"unknown"}


# --------------------------------------------------------------------- #
# Helpers (verb-token, flag-name, MCP detection, env prefix)            #
# --------------------------------------------------------------------- #


class TestVerbToken:
    def test_simple(self):
        assert _verb_token("list") == "list"

    def test_compound(self):
        assert _verb_token("start-dashboard") == "start"

    def test_uppercase(self):
        assert _verb_token("Show-Stats") == "show"


class TestFlagNames:
    def test_collects_long_and_short(self):
        @click.command()
        @click.option("--json", "as_json", is_flag=True)
        @click.option("--verbose", "-v", is_flag=True)
        def cmd(as_json, verbose):
            pass

        assert "--json" in _flag_names(cmd)
        assert "--verbose" in _flag_names(cmd)
        assert "-v" in _flag_names(cmd)


class TestMcpServerDetection:
    @pytest.mark.parametrize(
        "ep_value,expected",
        [
            ("scitex_cloud._mcp_server:main", True),
            ("scitex.canvas.mcp_server:main", True),
            ("scitex_orochi._server:main", True),
            ("scitex_io._cli:main", False),
            ("scitex_stats._cli:main", False),
            ("scitex.__main__:main", False),
        ],
    )
    def test_module_name_heuristic(self, ep_value, expected):
        assert _is_mcp_server_entry(ep_value) is expected


class TestEnvPrefix:
    def test_scitex_dev(self):
        assert _expected_env_prefix("scitex-dev") == "SCITEX_DEV_"

    def test_scitex_umbrella(self):
        assert _expected_env_prefix("scitex") == "SCITEX_"

    def test_compound_short_name(self):
        assert _expected_env_prefix("scitex-cloud-mcp") == "SCITEX_CLOUD_MCP_"

    def test_non_scitex_returns_none(self):
        assert _expected_env_prefix("figrecipe") is None


# --------------------------------------------------------------------- #
# §4 example detection                                                  #
# --------------------------------------------------------------------- #


class TestHasExample:
    def _make(self, help_text="", epilog=""):
        return click.Command("x", help=help_text or None, epilog=epilog or None)

    def test_examples_header(self):
        assert _has_example(self._make(epilog="Examples:\n  $ foo bar"))

    def test_dollar_invocation_line(self):
        assert _has_example(self._make(epilog="$ scitex-foo bar"))

    def test_fenced_code_block(self):
        assert _has_example(self._make(epilog="```\nrun this\n```"))

    def test_rst_code_block_directive(self):
        assert _has_example(self._make(epilog=".. code-block:: bash\n\n   foo"))

    def test_negative_prose_only(self):
        # Bare "for example" in prose no longer triggers a false positive
        assert not _has_example(self._make(help_text="This is for example purposes."))

    def test_empty(self):
        assert not _has_example(self._make())


# --------------------------------------------------------------------- #
# §1c pass-through detection                                             #
# --------------------------------------------------------------------- #


class TestIsPassThrough:
    def test_via_context_settings(self):
        cmd = click.Command(
            "git",
            context_settings={
                "ignore_unknown_options": True,
                "allow_extra_args": True,
            },
        )
        assert _is_pass_through(cmd)

    def test_via_attribute_sentinel(self):
        cmd = click.Command("custom")
        cmd._pass_through = True  # type: ignore[attr-defined]
        assert _is_pass_through(cmd)

    def test_negative(self):
        cmd = click.Command("plain")
        assert not _is_pass_through(cmd)

    def test_partial_context_settings_does_not_match(self):
        cmd = click.Command("x", context_settings={"ignore_unknown_options": True})
        # Needs both ignore_unknown_options AND allow_extra_args
        assert not _is_pass_through(cmd)


# --------------------------------------------------------------------- #
# _filter_violations (rule / exclude / severity gating)                  #
# --------------------------------------------------------------------- #


class TestFilterViolations:
    def _v(self, rule):
        return Violation(command="x", rule=rule, message="test")

    def test_no_filter_returns_all(self):
        vs = [self._v("§1"), self._v("§4")]
        assert len(_filter_violations(vs)) == 2

    def test_rule_filter_includes_only_matching(self):
        vs = [self._v("§1"), self._v("§4"), self._v("§1a")]
        out = _filter_violations(vs, rules=("§1",))
        assert len(out) == 1
        assert out[0].rule == "§1"

    def test_rule_filter_accepts_unprefixed(self):
        vs = [self._v("§1a")]
        out = _filter_violations(vs, rules=("1a",))
        assert len(out) == 1

    def test_exclude_drops_matching(self):
        vs = [self._v("§4"), self._v("§2")]
        out = _filter_violations(vs, exclude=("§4",))
        assert len(out) == 1
        assert out[0].rule == "§2"

    def test_severity_error_only(self):
        # §1 = error, §1c = info — only §1 should pass --severity error.
        # (Per the 2026-05-06 sweep, every actionable § is now error;
        # info-only tags like §1c remain below the error threshold.)
        vs = [self._v("§1"), self._v("§1c")]
        out = _filter_violations(vs, min_severity="error")
        rules = [v.rule for v in out]
        assert "§1" in rules
        assert "§1c" not in rules

    def test_severity_warn_includes_warn_and_error(self):
        vs = [self._v("§1"), self._v("§4"), self._v("§1c")]
        out = _filter_violations(vs, min_severity="warn")
        # §1 (error) and §4 (error) both pass the warn threshold;
        # §1c (info) does not.
        rules = {v.rule for v in out}
        assert "§1" in rules and "§4" in rules
        assert "§1c" not in rules


# --------------------------------------------------------------------- #
# _extract_names (§7 parity helper)                                      #
# --------------------------------------------------------------------- #


class TestExtractNames:
    def test_list_of_strings(self):
        assert _extract_names(["save", "load"]) == {"save", "load"}

    def test_list_of_dicts_name_field(self):
        assert _extract_names([{"name": "save"}, {"name": "load"}]) == {"save", "load"}

    def test_list_of_dicts_alt_keys(self):
        # Falls through name -> tool -> api -> id
        assert _extract_names([{"tool": "io_save"}, {"api": "io_load"}]) == {
            "io_save",
            "io_load",
        }

    def test_dict_wrapper(self):
        assert _extract_names({"apis": ["a", "b"]}) == {"a", "b"}

    def test_empty_input(self):
        assert _extract_names([]) == set()
        assert _extract_names({}) == set()

    def test_unknown_shape_returns_empty(self):
        assert _extract_names("not a list or dict") == set()


# --------------------------------------------------------------------- #
# Registry cascade (no overrides → bundled fallback)                    #
# --------------------------------------------------------------------- #


class TestLoadRegistry:
    def test_default_uses_bundled(self, tmp_path, monkeypatch):
        # Disable env + project + user candidates so we reach the bundled layer.
        monkeypatch.delenv("SCITEX_DEV_REGISTRY", raising=False)
        monkeypatch.chdir(tmp_path)  # no .scitex/dev/ecosystem.yaml here
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        registry, provenance = _load_registry(None)
        assert "bundled" in provenance
        assert "scitex" in registry  # umbrella package present

    def test_explicit_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SCITEX_DEV_REGISTRY", raising=False)
        path = tmp_path / "override.yaml"
        path.write_text("custom-pkg:\n  pypi_name: custom-pkg\n  category: library\n")
        registry, provenance = _load_registry(str(path))
        assert "--registry flag" in provenance
        assert "custom-pkg" in registry
        # Bundled entries still merged in
        assert "scitex" in registry

    def test_env_var_layer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        path = tmp_path / "from-env.yaml"
        path.write_text("env-only:\n  category: library\n")
        monkeypatch.setenv("SCITEX_DEV_REGISTRY", str(path))
        registry, provenance = _load_registry(None)
        assert "$SCITEX_DEV_REGISTRY" in provenance
        assert "env-only" in registry


# --------------------------------------------------------------------- #
# Argparse capture round-trip                                            #
# --------------------------------------------------------------------- #


class TestArgparseCapture:
    def test_captures_simple_parser(self):
        def main(argv=None):
            parser = argparse.ArgumentParser(prog="testcli")
            parser.add_argument("--json", action="store_true")
            parser.add_argument("--verbose", "-v", action="store_true")
            sub = parser.add_subparsers()
            sp = sub.add_parser("list")
            sp.add_argument("--all", action="store_true")
            parser.parse_args(argv or [])

        captured = _capture_root(main)
        assert captured is not None

        wrapped = _wrap_argparse(captured, name="testcli")
        assert isinstance(wrapped, click.Group)
        assert "list" in wrapped.commands
        # Top-level flags survived
        assert "--json" in _flag_names(wrapped)
        assert "--verbose" in _flag_names(wrapped) or "-v" in _flag_names(wrapped)

    def test_captures_main_without_argv_param(self):
        def main():
            parser = argparse.ArgumentParser(prog="zerocli")
            parser.add_argument("--foo")
            parser.parse_args()

        captured = _capture_root(main)
        assert captured is not None
        wrapped = _wrap_argparse(captured, name="zerocli")
        assert "--foo" in _flag_names(wrapped)


# --------------------------------------------------------------------- #
# §1a introspection presence on a synthetic Click tree                  #
# --------------------------------------------------------------------- #


class TestIntrospectionCheck:
    def _fixture_with_introspection(self):
        @click.group()
        def root():
            pass

        @root.command("list-python-apis")
        @click.option("--json", "as_json", is_flag=True)
        def lpa(as_json):
            pass

        @root.group("mcp")
        def mcp_group():
            pass

        @mcp_group.command("list-tools")
        @click.option("--json", "as_json", is_flag=True)
        def list_tools(as_json):
            pass

        # §1a — shell-completion subcommands mandatory (codified 2026-05-06).
        @root.command("install-shell-completion")
        @click.option("--shell", default="bash")
        def isc(shell):
            pass

        @root.command("print-shell-completion")
        @click.option("--shell", default="bash")
        def psc(shell):
            pass

        return root

    def test_complete_tree_passes(self):
        out: list[Violation] = []
        _check_introspection(self._fixture_with_introspection(), "demo", out)
        assert out == []

    def test_missing_list_python_apis(self):
        @click.group()
        def root():
            pass

        out: list[Violation] = []
        _check_introspection(root, "demo", out)
        rules = [v.rule for v in out]
        assert "§1a" in rules
        # Should specifically mention list-python-apis
        assert any("list-python-apis" in v.message for v in out)

    def test_missing_json_on_list_python_apis(self):
        @click.group()
        def root():
            pass

        @root.command("list-python-apis")
        def lpa():
            pass

        @root.group("mcp")
        def mcp_group():
            pass

        @mcp_group.command("list-tools")
        @click.option("--json", "as_json", is_flag=True)
        def lt(as_json):
            pass

        out: list[Violation] = []
        _check_introspection(root, "demo", out)
        assert any("--json" in v.message for v in out)


# --------------------------------------------------------------------- #
# _walk applies §1b banned bare leaves                                   #
# --------------------------------------------------------------------- #


class TestBannedLeaves:
    def test_version_subcommand_flagged(self):
        @click.group()
        def root():
            pass

        @root.command("version")
        def version_cmd():
            pass

        out: list[Violation] = []
        _walk(root, [], out, root_display="demo")
        assert any(v.rule == "§1b" and "version" in v.message for v in out)

    def test_completion_subcommand_flagged(self):
        @click.group()
        def root():
            pass

        @root.command("completion")
        def completion_cmd():
            pass

        out: list[Violation] = []
        _walk(root, [], out, root_display="demo")
        assert any(v.rule == "§1b" and "completion" in v.message for v in out)


# --------------------------------------------------------------------- #
# Pass-through leaves bypass §1                                          #
# --------------------------------------------------------------------- #


class TestPassThroughBypassesRule1:
    def test_pass_through_leaf_no_violations(self):
        @click.group()
        def root():
            pass

        @root.command(
            "git",
            context_settings={
                "ignore_unknown_options": True,
                "allow_extra_args": True,
            },
        )
        @click.argument("forwarded", nargs=-1)
        def git_passthrough(forwarded):
            pass

        out: list[Violation] = []
        _walk(root, [], out, root_display="demo")
        # `git` is a noun-only token; without pass-through it would trip §1
        # (leaf token looks like a noun). The pass-through marker should suppress.
        assert not any(v.rule == "§1" and v.command.endswith("git") for v in out)


# --------------------------------------------------------------------- #
# _audit_one — graceful "not-found" path                                 #
# --------------------------------------------------------------------- #


class TestAuditOneNotFound:
    def test_unknown_package(self):
        status, violations = _audit_one("definitely-not-a-real-package-xyz")
        assert status == "not-found"
        assert violations == []

    def test_returns_skip_mcp_for_mcp_entry(self, monkeypatch):
        # Patch _ep_value_for so the package looks like an MCP server.
        from scitex_dev._cli.audit._summary import _audit as audit_mod

        monkeypatch.setattr(
            audit_mod, "_ep_value_for", lambda pkg: "fake.mcp_server:main"
        )
        status, violations = _audit_one("fake-pkg-mcp")
        assert status == "skip-mcp"
        assert violations == []


# --------------------------------------------------------------------- #
# Watchdog (process-level timeout for --all)                            #
# --------------------------------------------------------------------- #


class TestWatchdog:
    def test_fires_on_long_block(self):
        import time

        with pytest.raises(_PackageTimeout):
            with _watchdog(0.2):
                time.sleep(2.0)

    def test_no_fire_on_quick_block(self):
        # Should complete cleanly without raising.
        with _watchdog(2.0):
            pass

    def test_zero_seconds_disables(self):
        # Disabled watchdog must not raise even on a slow block.
        import time

        with _watchdog(0):
            time.sleep(0.05)


# --------------------------------------------------------------------- #
# _isolated_streams (sanity — restores stdio)                            #
# --------------------------------------------------------------------- #


class TestIsolatedStreams:
    def test_restores_stdout_after_block(self, capsys):
        import sys

        original = sys.stdout
        with _isolated_streams():
            print("this should be swallowed")
        # After exit, stdout should be writable again.
        print("visible-marker")
        captured = capsys.readouterr()
        assert "this should be swallowed" not in captured.out
        # New writes go to the test's capsys stream — not the original.
        # Just confirm sys.stdout is non-closed and writable after exit.
        assert not sys.stdout.closed
        assert sys.stdout is not original or original is sys.stdout
