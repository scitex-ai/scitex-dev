#!/usr/bin/env python3
"""Tests for §1 noun-verb homonym tightening + §1e server-startup-flag rule.

Operator directive 13316 (lead a2a `6ea19fd4...` 2026-06-14): `scitex-todo
board --port 8051` was silently passed by audit-cli because Moby POS
classifies "board" as both noun (the surface) AND verb-i/verb-t ("to board
a flight"). The §1 leaf-noun rule's exemption fired on the Moby verb labels
and skipped the violation.

This module covers BOTH halves of the fix:

* PART A — top-level (depth=1) leaf that classifies as noun-AND-verb is
  no longer auto-exempted. Nested leaves (depth≥2) keep the original
  permissive behaviour (they're verb-by-context).
* PART B — new §1e rule: a top-level noun leaf accepting any of
  `--port / --host / --bind / --serve / --daemon / --workers / --listen /
  --addr / --address` is unambiguously starting a service and must be
  `start-<noun>` or nested under a `<noun>` group with a `start` verb.

No mocks — every test wires a real ``click.Group`` and walks it.
"""

from __future__ import annotations

import click

from scitex_dev._cli.audit._summary._audit import (
    SERVER_STARTUP_FLAGS,
    Violation,
    _walk,
)


# --------------------------------------------------------------------------- #
# PART A — §1 catches multi-class noun-verb homonyms at top level             #
# --------------------------------------------------------------------------- #


class TestNounVerbHomonymAtTopLevelIsFlagged:
    """A noun-verb homonym leaf at depth=1 must trip §1 regardless of
    Moby also-verb labels. Pre-fix behaviour silently exempted these.
    """

    def test_board_top_level_leaf_flagged(self):
        # Arrange — `scitex-todo board` with no subcommands.
        @click.group()
        def root():
            pass

        @root.command("board")
        def board_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§1" and v.command.endswith("board") for v in out), (
            "depth=1 multi-class noun-verb homonym must trip §1"
        )

    def test_violation_message_mentions_dict_escape_hatch(self):
        # Arrange — operator wants the actionable hint inline in the
        # violation, not buried in docs.
        @click.group()
        def root():
            pass

        @root.command("board")
        def board_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        msgs = [v.message for v in out if v.rule == "§1" and "board" in v.message]
        assert msgs, "expected at least one §1 violation for `board`"
        combined = " ".join(msgs).lower()
        assert "intransitive_verbs" in combined or "cli-audit-dict.yaml" in combined

    def test_panel_top_level_leaf_flagged(self):
        # Arrange — `panel` is another noun-verb homonym (Moby labels:
        # noun + verb + verb-t).
        @click.group()
        def root():
            pass

        @root.command("panel")
        def panel_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§1" and v.command.endswith("panel") for v in out)


class TestNounVerbHomonymNestedIsNotFlaggedByPartA:
    """At depth≥2 the historical permissive behaviour stays: nested
    leaves are verb-by-context (the parent group is the noun).
    """

    def test_board_under_app_group_does_not_trip_part_a(self):
        # Arrange — `scitex-todo app board` — nested under `app`.
        @click.group()
        def root():
            pass

        @root.group()
        def app():
            pass

        @app.command("board")
        def board_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — depth=2 leaf must NOT trip PART A's tightening.
        offending = [v for v in out if v.rule == "§1" and v.command.endswith("board")]
        assert offending == [], (
            "nested noun-verb homonym should keep the permissive exemption "
            "because the parent group provides the noun context"
        )


class TestNounOnlyLeavesStillFlaggedAtAllDepths:
    """Sanity: the existing noun-only path (e.g. `server`, `cache`) must
    keep firing — we tightened, we did NOT loosen.
    """

    def test_cache_top_level_leaf_still_flagged(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("cache")
        def cache_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§1" and v.command.endswith("cache") for v in out)


# --------------------------------------------------------------------------- #
# PART B — §1e server-startup-flag heuristic                                 #
# --------------------------------------------------------------------------- #


class TestServerStartupFlagsConstant:
    """The constant itself is the contract — any change here is operator-
    visible (drives the §1e violation message)."""

    def test_constant_includes_port(self):
        # Arrange + Act + Assert
        assert "--port" in SERVER_STARTUP_FLAGS

    def test_constant_includes_host_bind_serve(self):
        # Arrange + Act + Assert
        for f in ("--host", "--bind", "--serve"):
            assert f in SERVER_STARTUP_FLAGS

    def test_constant_includes_daemon_workers_listen_addr_address(self):
        # Arrange + Act + Assert
        for f in ("--daemon", "--workers", "--listen", "--addr", "--address"):
            assert f in SERVER_STARTUP_FLAGS

    def test_constant_does_not_include_common_non_server_flag(self):
        # Arrange + Act + Assert — `--json` is a §2 read-verb flag, not a
        # server-startup signal. Adding it would create false positives.
        assert "--json" not in SERVER_STARTUP_FLAGS


class TestRule1eServerStartupFlagFires:
    """The exact operator-flagged pattern: `<tool> <noun> --port N`."""

    def test_board_with_port_flag_flagged_by_1e(self):
        # Arrange — the operator's exact case.
        @click.group()
        def root():
            pass

        @root.command("board")
        @click.option("--port", type=int, default=8051)
        def board_cmd(port):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§1e" and v.command.endswith("board") for v in out)

    def test_cache_with_port_flag_flagged_by_1e(self):
        # Arrange — `cache` is noun-only; the §1 rule already fires, but
        # §1e fires ON TOP because the server-flag pattern is present.
        @click.group()
        def root():
            pass

        @root.command("cache")
        @click.option("--port", type=int, default=6379)
        def cache_cmd(port):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — both §1 and §1e fire (different rule ids — they're
        # complementary signals to the user).
        rules = {(v.rule, v.command) for v in out}
        assert ("§1", "demo cache") in rules
        assert ("§1e", "demo cache") in rules

    def test_dashboard_with_bind_flag_flagged_by_1e(self):
        # Arrange — `--bind` is the gunicorn / uvicorn signal.
        @click.group()
        def root():
            pass

        @root.command("dashboard")
        @click.option("--bind", default="127.0.0.1:8000")
        def dashboard_cmd(bind):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§1e" and "dashboard" in v.command for v in out)


class TestRule1eDoesNotFireOnNonServerFlags:
    def test_noun_leaf_without_server_flags_does_not_trip_1e(self):
        # Arrange — `board` with a non-server flag. §1 still fires (it's
        # a top-level noun leaf), but §1e MUST NOT — otherwise we'd
        # double-flag with a wrong rule id.
        @click.group()
        def root():
            pass

        @root.command("board")
        @click.option("--json", is_flag=True)
        def board_cmd(json):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(v.rule != "§1e" for v in out)


class TestRule1eDoesNotFireOnNestedNounLeaves:
    """§1e is top-level-only. Nested `<noun-group> <verb>` is correct
    grammar — the nested leaf carries the server-startup flags as part
    of a properly-named verb subcommand.
    """

    def test_board_start_under_app_does_not_trip_1e(self):
        # Arrange — `demo app start` with --port — correct shape.
        @click.group()
        def root():
            pass

        @root.group()
        def app():
            pass

        @app.command("start")
        @click.option("--port", type=int, default=8051)
        def start_cmd(port):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(v.rule != "§1e" for v in out)


class TestRule1eCompoundLeafIsCorrectGrammar:
    """`start-board --port 8051` is the FIX shape that the violation
    message points to — it must not itself trip §1e (otherwise the
    rule is unactionable)."""

    def test_compound_start_board_with_port_does_not_trip_1e(self):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("start-board")
        @click.option("--port", type=int, default=8051)
        def start_board_cmd(port):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(not (v.rule == "§1e" and "start-board" in v.command) for v in out)
