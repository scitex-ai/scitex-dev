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
import pytest

from scitex_dev._cli.audit._summary._audit import (
    SERVER_STARTUP_FLAGS,
    Violation,
    _group_head_labels,
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
        # violation, not buried in docs. `any(...)` keeps the assertion
        # single while still asserting the substring presence across
        # whatever §1 violations the walker emits for `board`.
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
        assert any(
            v.rule == "§1"
            and "board" in v.message
            and (
                "intransitive_verbs" in v.message.lower()
                or "cli-audit-dict.yaml" in v.message.lower()
            )
            for v in out
        )

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


class TestCompoundLeafIsNotFlaggedByPartA:
    """Compounds like `print-shell-completion` (verb-noun) are the FIX
    shape the §1 violation message points to — they must NOT themselves
    trip PART A, even though their head token (`print`) is a Moby
    noun-verb homonym. Guards against the regression we caught on
    scitex-dev's own CLI surface during the first CI roll.
    """

    def test_print_shell_completion_top_level_compound_not_flagged(self):
        # Arrange — `print-shell-completion` is correct grammar.
        @click.group()
        def root():
            pass

        @root.command("print-shell-completion")
        def print_completion_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(
            not (v.rule == "§1" and "print-shell-completion" in v.command) for v in out
        )


# --------------------------------------------------------------------------- #
# PART B — §1e server-startup-flag heuristic                                 #
# --------------------------------------------------------------------------- #


class TestServerStartupFlagsConstant:
    """The constant itself is the contract — any change here is operator-
    visible (drives the §1e violation message)."""

    @pytest.mark.parametrize(
        "flag",
        [
            "--port",
            "--host",
            "--bind",
            "--serve",
            "--daemon",
            "--workers",
            "--listen",
            "--addr",
            "--address",
        ],
    )
    def test_constant_includes_expected_server_startup_flag(self, flag):
        # Arrange
        constant = SERVER_STARTUP_FLAGS
        # Act
        is_present = flag in constant
        # Assert
        assert is_present

    def test_constant_does_not_include_common_non_server_flag(self):
        # Arrange — `--json` is a §2 read-verb flag, not a server-startup
        # signal. Adding it would create false positives.
        constant = SERVER_STARTUP_FLAGS
        # Act
        is_present = "--json" in constant
        # Assert
        assert not is_present


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
        # Arrange — `cache` is noun-only; the §1 rule already fires
        # independently. This test guards §1e, the new rule.
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
        # Assert
        rules = {(v.rule, v.command) for v in out}
        assert ("§1e", "demo cache") in rules

    def test_cache_with_port_flag_still_flagged_by_section_1(self):
        # Arrange — sister test guarding that §1 also still fires on
        # the same fixture (§1 and §1e are complementary signals to
        # the user; both ids must surface, with different texts).
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
        # Assert
        rules = {(v.rule, v.command) for v in out}
        assert ("§1", "demo cache") in rules

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


# --------------------------------------------------------------------------- #
# §1 — group token must be a NOUN, judged by the token's semantic HEAD.        #
#                                                                             #
# Regression: `_classify` classifies a hyphenated token by its FIRST part     #
# (its compound fallback). For a GROUP that wrongly inherited verb-ness from   #
# the leading MODIFIER, so a legit compound-noun group whose head is a noun    #
# (`login-guardrail` = a *guardrail*) was flagged "group token looks like a    #
# verb — non-leaf subcommands must be nouns". This over-flag broke consumer    #
# CI (e.g. an ecosystem package exposing a `login-guardrail` group). The fix   #
# classifies the HEAD (right-headed English noun compound) so compound nouns   #
# pass while genuinely verb-named single-token groups (`run`, `build`) still   #
# flag. No mocks — real `click.Group` trees walked end to end.                 #
# --------------------------------------------------------------------------- #


class TestGroupHeadLabelsHelper:
    """`_group_head_labels` classifies by the HEAD (last hyphen part)."""

    def test_single_token_verb_group_is_verb(self):
        # Arrange
        token = "login"
        # Act
        labels = _group_head_labels(token)
        # Assert — a bare verb group keeps its verb label (no noun).
        assert ({"verb-t", "verb-i", "verb"} & labels) and "noun" not in labels

    def test_compound_noun_group_head_is_noun(self):
        # Arrange — head `guardrail` is a plain noun.
        token = "login-guardrail"
        # Act
        labels = _group_head_labels(token)
        # Assert — the leading `login` verb no longer leaks in.
        assert "noun" in labels and not ({"verb-t", "verb-i", "verb"} & labels)

    def test_single_noun_group_is_noun(self):
        # Arrange
        token = "guardrail"
        # Act
        labels = _group_head_labels(token)
        # Assert
        assert "noun" in labels


class TestCompoundNounGroupNotFlaggedByRule1:
    """The confirmed over-flag regression: a compound-noun group whose
    leading modifier is a verb stem must NOT trip §1."""

    def test_login_guardrail_group_not_flagged(self):
        # Arrange — `login-guardrail` is a noun (a guardrail for login).
        @click.group()
        def root():
            pass

        @root.group("login-guardrail")
        def login_guardrail_group():
            pass

        @login_guardrail_group.command("list")
        @click.option("--json", "as_json", is_flag=True)
        def list_cmd(as_json):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — no §1 "looks like a verb" flag on the compound-noun group.
        assert all(
            not (v.rule == "§1" and v.command.endswith("login-guardrail"))
            for v in out
        )

    def test_build_cache_group_not_flagged(self):
        # Arrange — `build-cache` is a noun (a cache of builds); head `cache`
        # is a noun. The leading `build` verb must not leak in.
        @click.group()
        def root():
            pass

        @root.group("build-cache")
        def build_cache_group():
            pass

        @build_cache_group.command("list")
        @click.option("--json", "as_json", is_flag=True)
        def list_cmd(as_json):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(
            not (v.rule == "§1" and v.command.endswith("build-cache")) for v in out
        )


class TestVerbNamedGroupStillFlaggedByRule1:
    """True positive preserved: a genuinely verb-named single-token group
    (the head IS the verb) must still trip §1."""

    def test_run_group_flagged(self):
        # Arrange — `run` classifies as a verb; a verb-named group is wrong
        # grammar (groups are nouns).
        @click.group()
        def root():
            pass

        @root.group("build")
        def build_group():
            pass

        @build_group.command("list")
        @click.option("--json", "as_json", is_flag=True)
        def list_cmd(as_json):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — `build` is a transitive verb; a verb-named group trips §1.
        assert any(
            v.rule == "§1"
            and v.command.endswith("build")
            and "looks like a verb" in v.message
            for v in out
        )
