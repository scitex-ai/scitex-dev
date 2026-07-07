#!/usr/bin/env python3
"""Tests for slice-4 CLI-standardization rules (`_std_rules`).

Covers:

* §1f — non-canonical verb synonyms (doctrine 06 tables): warn fires on
  synonym verb tokens AND full-leaf-name forms; `verb_exceptions:` in
  `.scitex/dev/cli-audit-dict.yaml` suppresses; an exception entry
  without a `# why` comment is itself warned about; §1a-mandated
  commands (`print-shell-completion`) are built-in exempt.
* §4b — help not built from a CliHelp spec: fires on free-form commands,
  not on SpecCommand/SpecGroup; the `_has_example` sniff (§4) is
  subsumed for spec-built commands.
§5 deprecation-ladder coverage lives in
`test__std_rules_deprecation.py` (same-module split, 512-line cap).

No mocks — real click trees, real dict files in a sandboxed cwd.
"""

from __future__ import annotations

import os

import pytest

click = pytest.importorskip("click")

from scitex_dev._cli.audit._summary._audit import (
    Violation,
    _check_help_format,
    _walk,
)
from scitex_dev._cli.audit._summary._std_rules import (
    VERB_SYNONYMS,
    check_spec_built_help,
    check_verb_exception_comments,
    load_verb_exceptions,
)
from scitex_dev._ecosystem.help_spec import CliHelp, Example, SpecCommand


@pytest.fixture
def cwd_sandbox(tmp_path):
    """Sandboxed cwd + HOME so the layered cli-audit-dict.yaml lookups
    (cwd first, then ~) resolve inside tmp_path only.
    """
    saved_cwd = os.getcwd()
    saved_home = os.environ.get("HOME")
    os.chdir(tmp_path)
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(saved_cwd)
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home


def _write_dict(tmp_path, text: str) -> None:
    """Write a project-layer cli-audit-dict.yaml under the sandbox cwd."""
    dict_dir = tmp_path / ".scitex" / "dev"
    dict_dir.mkdir(parents=True, exist_ok=True)
    (dict_dir / "cli-audit-dict.yaml").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# §1f — the synonym map itself (the contract)                                  #
# --------------------------------------------------------------------------- #


class TestVerbSynonymsMapContract:
    """Every row traces to a doctrine 06 table — spot-check the seeds the
    proposal names explicitly."""

    @pytest.mark.parametrize(
        "synonym",
        ["ls", "resolve", "complete", "setup", "sync-to", "sync-from", "show-status"],
    )
    def test_map_contains_proposal_seed_synonym(self, synonym):
        # Arrange
        mapping = VERB_SYNONYMS
        # Act
        is_present = synonym in mapping
        # Assert
        assert is_present

    def test_map_does_not_contain_canonical_verb_list(self):
        # Arrange — canonical verbs must never appear as keys (they are
        # the TARGETS, not the synonyms).
        mapping = VERB_SYNONYMS
        # Act
        canonical_present = {"list", "get", "create", "delete", "done"} & set(mapping)
        # Assert
        assert canonical_present == set()

    def test_resolve_maps_to_done_terminal_verb(self):
        # Arrange
        mapping = VERB_SYNONYMS
        # Act
        target = mapping["resolve"]
        # Assert
        assert target.startswith("done")


# --------------------------------------------------------------------------- #
# §1f — walker integration                                                     #
# --------------------------------------------------------------------------- #


class TestRule1fFiresOnSynonyms:
    def test_resolve_card_leaf_warns_via_verb_token(self, cwd_sandbox):
        # Arrange — `resolve-card` carries the banned terminal verb.
        @click.group()
        def root():
            pass

        @root.command("resolve-card")
        def resolve_card_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(
            v.rule == "§1f" and v.command == "demo resolve-card" for v in out
        )

    def test_show_status_leaf_warns_via_full_name(self, cwd_sandbox):
        # Arrange — `show-status` is a full-leaf-name synonym row (its
        # verb token `show` alone is canonical).
        @click.group()
        def root():
            pass

        @root.command("show-status")
        def show_status_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(
            v.rule == "§1f" and v.command == "demo show-status" for v in out
        )

    def test_violation_message_names_canonical_replacement(self, cwd_sandbox):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("resolve-card")
        def resolve_card_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — the fix (done) is inline in the message.
        assert any(v.rule == "§1f" and "done" in v.message for v in out)


class TestRule1fDoesNotFireOnCanonicalVerbs:
    def test_list_leaf_not_flagged_by_1f(self, cwd_sandbox):
        # Arrange — `list-cards` uses the canonical verb.
        @click.group()
        def root():
            pass

        @root.command("list-cards")
        @click.option("--json", "as_json", is_flag=True)
        def list_cards_cmd(as_json):
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(v.rule != "§1f" for v in out)

    def test_print_shell_completion_is_builtin_exempt(self, cwd_sandbox):
        # Arrange — §1a REQUIRES this exact command; its `print` head
        # must not warn even though `print` maps to `show`.
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
        assert all(v.rule != "§1f" for v in out)


class TestRule1fVerbExceptions:
    def test_exception_with_why_comment_suppresses_warning(self, cwd_sandbox):
        # Arrange — repo opts `resolve` out with a documented why.
        _write_dict(
            cwd_sandbox,
            "verb_exceptions:\n"
            "  - resolve  # why: matches upstream GitHub issue terminology\n",
        )

        @click.group()
        def root():
            pass

        @root.command("resolve-card")
        def resolve_card_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(v.rule != "§1f" for v in out)

    def test_exception_full_leaf_name_also_suppresses(self, cwd_sandbox):
        # Arrange — the exception can name the full leaf, not just the verb.
        _write_dict(
            cwd_sandbox,
            "verb_exceptions:\n"
            "  - show-status  # why: legacy scripts pinned until v0.30\n",
        )

        @click.group()
        def root():
            pass

        @root.command("show-status")
        def show_status_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(v.rule != "§1f" for v in out)

    def test_exception_without_why_comment_is_warned_about(self, cwd_sandbox):
        # Arrange — undocumented exception entry.
        _write_dict(cwd_sandbox, "verb_exceptions:\n  - resolve\n")
        out: list[Violation] = []
        # Act
        check_verb_exception_comments("demo", out)
        # Assert
        assert any(
            v.rule == "§1f" and "resolve" in v.message and "# why" in v.message
            for v in out
        )

    def test_exception_with_why_comment_not_warned_about(self, cwd_sandbox):
        # Arrange
        _write_dict(
            cwd_sandbox,
            "verb_exceptions:\n  - resolve  # why: upstream terminology\n",
        )
        out: list[Violation] = []
        # Act
        check_verb_exception_comments("demo", out)
        # Assert
        assert out == []

    def test_load_verb_exceptions_reports_missing_why_entry(self, cwd_sandbox):
        # Arrange — one documented, one undocumented entry.
        _write_dict(
            cwd_sandbox,
            "verb_exceptions:\n"
            "  - resolve  # why: upstream terminology\n"
            "  - setup\n",
        )
        # Act
        _exceptions, missing_why = load_verb_exceptions()
        # Assert
        assert [entry for entry, _path in missing_why] == ["setup"]

    def test_load_verb_exceptions_returns_both_entries(self, cwd_sandbox):
        # Arrange
        _write_dict(
            cwd_sandbox,
            "verb_exceptions:\n"
            "  - resolve  # why: upstream terminology\n"
            "  - setup\n",
        )
        # Act
        exceptions, _missing_why = load_verb_exceptions()
        # Assert — undocumented entries still exempt (the missing-why is
        # its own §1f finding, not a silent drop of the exception).
        assert exceptions == {"resolve", "setup"}


# --------------------------------------------------------------------------- #
# §4b — help not built from spec                                                #
# --------------------------------------------------------------------------- #


def _spec_leaf(name: str) -> SpecCommand:
    """A real spec-built leaf (validated CliHelp with one example)."""
    return SpecCommand(
        name,
        callback=lambda: None,
        help_spec=CliHelp(
            summary="Do the demo thing.",
            examples=(Example("{prog} " + name, "Run it."),),
        ),
    )


class TestRule4bFiresOnFreeFormHelp:
    def test_free_form_leaf_warns_4b(self, cwd_sandbox):
        # Arrange — plain click.Command with docstring help.
        @click.group()
        def root():
            pass

        @root.command("list-cards")
        @click.option("--json", "as_json", is_flag=True)
        def list_cards_cmd(as_json):
            """List cards.

            Example:
              $ demo list-cards
            """

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(
            v.rule == "§4b" and v.command == "demo list-cards" for v in out
        )

    def test_4b_message_points_at_help_spec_module(self, cwd_sandbox):
        # Arrange
        @click.group()
        def root():
            pass

        @root.command("list-cards")
        def list_cards_cmd():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert — exact remediation string from the spec.
        assert any(
            v.rule == "§4b"
            and "construct via CliHelp (scitex_dev.ecosystem.help_spec)" in v.message
            for v in out
        )

    def test_free_form_root_also_warns_4b(self, cwd_sandbox):
        # Arrange — the root group itself should be spec-built (SpecGroup).
        @click.group()
        def root():
            pass

        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert any(v.rule == "§4b" and v.command == "demo" for v in out)


class TestRule4bDoesNotFireOnSpecBuilt:
    def test_spec_command_leaf_passes_4b(self, cwd_sandbox):
        # Arrange — real SpecCommand carries `_help_spec`.
        @click.group()
        def root():
            pass

        root.add_command(_spec_leaf("run-demo"))
        out: list[Violation] = []
        # Act
        _walk(root, [], out, root_display="demo")
        # Assert
        assert all(
            not (v.rule == "§4b" and v.command == "demo run-demo") for v in out
        )

    def test_check_spec_built_help_accepts_spec_command_directly(self):
        # Arrange
        cmd = _spec_leaf("run-demo")
        out: list[Violation] = []
        # Act
        check_spec_built_help(cmd, "demo run-demo", out)
        # Assert
        assert out == []


class TestRule4bSubsumesExampleSniff:
    def test_spec_built_command_skips_section4_example_check(self):
        # Arrange — a plain command with NO example markers but carrying
        # a `_help_spec` (spec validation guarantees examples, so the §4
        # sniff must not double-flag). Real attribute on a real command,
        # exactly what SpecCommand.__init__ sets.
        cmd = click.Command("run-demo", callback=lambda: None, help="No markers here.")
        cmd._help_spec = CliHelp(
            summary="Do the demo thing.",
            examples=(Example("{prog} run-demo", "Run it."),),
        )
        out: list[Violation] = []
        # Act
        _check_help_format(cmd, "demo run-demo", out)
        # Assert
        assert out == []

    def test_free_form_command_without_example_still_flagged_by_section4(self):
        # Arrange — sanity: the §4 sniff still fires without `_help_spec`.
        cmd = click.Command("run-demo", callback=lambda: None, help="No markers here.")
        out: list[Violation] = []
        # Act
        _check_help_format(cmd, "demo run-demo", out)
        # Assert
        assert any(v.rule == "§4" for v in out)


# §5 deprecation-ladder tests (static metadata + phase-aware behavioral
# assessment) live in `test__std_rules_deprecation.py` — split to keep
# each test module under the 512-line cap.
