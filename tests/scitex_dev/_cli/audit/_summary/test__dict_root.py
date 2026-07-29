#!/usr/bin/env python3
"""Tests for `_summary/_dict_root` — WHICH tree audit-cli's dictionary comes from.

Regression subject (scitex-storage vs scitex-dev v0.38.1): audit-cli read
`.scitex/dev/cli-audit-dict.yaml` from `Path.cwd()` regardless of
`--path`, so `audit-all <pkg> --path <worktree>` graded the pinned tree's
SOURCE against a different tree's DICTIONARY. Four sub-auditors printed
`via explicit` while audit-cli silently graded another checkout, and the
run's output looked internally consistent — which is what made it cost
minutes instead of seconds.

`TestPinnedDictRootIsRead` is the regression test proper: a §1f violation
whose fix lives ONLY in the pinned tree must disappear when that tree is
pinned while the cwd is elsewhere. `TestPinnedTreeStillFindsRealViolations`
is its positive control — the same pin must NOT turn the auditor blind:
a genuine violation that lives in the pinned tree is still reported, and
is reported against the PINNED file's path.

No mocks (PA-306 / STX-NM002): real tmp_path trees, real YAML files, and
the same public `use_dict_root` seam the production CLI uses.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scitex_dev._cli.audit._summary._dict_root import (
    dict_candidate_paths,
    dict_source_report,
    load_custom_dict,
    resolved_dict_root,
    use_dict_root,
)
from scitex_dev._cli.audit._summary._std_rules import (
    check_verb_exception_comments,
    check_verb_synonym,
    load_verb_exceptions,
)


def _write_dict(root: Path, text: str) -> Path:
    """Materialise `<root>/.scitex/dev/cli-audit-dict.yaml`; return its path."""
    dict_dir = root / ".scitex" / "dev"
    dict_dir.mkdir(parents=True, exist_ok=True)
    path = dict_dir / "cli-audit-dict.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def elsewhere(tmp_path):
    """A cwd + HOME that is NOT the audited tree and has NO dictionary.

    The whole defect only shows up when the cwd differs from the pinned
    tree, so every test here runs from a deliberately barren cwd.
    """
    barren = tmp_path / "elsewhere"
    barren.mkdir()
    saved_cwd = os.getcwd()
    saved_home = os.environ.get("HOME")
    os.chdir(barren)
    os.environ["HOME"] = str(barren)
    try:
        yield barren
    finally:
        os.chdir(saved_cwd)
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home


@pytest.fixture
def pinned_tree(tmp_path):
    """A checkout whose dict EXEMPTS `ls` — the fix lives only here."""
    tree = tmp_path / "worktree"
    tree.mkdir()
    _write_dict(
        tree,
        "verb_exceptions:\n"
        "  - ls  # why: vendored third-party CLI, rename is not ours to make\n",
    )
    return tree


# --------------------------------------------------------------------------- #
# THE REGRESSION: a violation whose fix lives only in the pinned tree          #
# --------------------------------------------------------------------------- #


class TestPinnedDictRootIsRead:
    """`--path <tree>` must make audit-cli read `<tree>`'s dictionary."""

    def test_unpinned_cwd_without_the_fix_still_reports_the_violation(
        self, elsewhere
    ):
        """Control: from a tree with no dict, §1f fires on `ls`."""
        # Arrange
        out: list = []
        # Act
        check_verb_synonym("ls", "demo ls", out)
        # Assert
        assert [v.rule for v in out] == ["§1f"]

    def test_pinning_the_tree_that_holds_the_fix_clears_the_violation(
        self, elsewhere, pinned_tree
    ):
        """THE BUG: cwd has no fix, the pinned tree does — pin must win.

        On origin/develop the dictionary was read from `Path.cwd()`
        regardless of the pinned tree, so the exemption in `pinned_tree`
        was never seen and this violation survived.
        """
        # Arrange
        out: list = []
        # Act
        with use_dict_root(pinned_tree, "explicit"):
            check_verb_synonym("ls", "demo ls", out)
        # Assert
        assert out == []

    def test_pin_does_not_leak_past_its_context(self, elsewhere, pinned_tree):
        """The pin is scoped: after the `with`, the cwd rule is back."""
        # Arrange
        with use_dict_root(pinned_tree, "explicit"):
            pass
        # Act
        root, via = resolved_dict_root()
        # Assert
        assert (root.resolve(), via) == (elsewhere.resolve(), "cwd")

    def test_pinned_exemption_is_actually_loaded(self, elsewhere, pinned_tree):
        """The exemption token itself comes back from the pinned tree."""
        # Arrange
        exceptions: set[str] = set()
        # Act
        with use_dict_root(pinned_tree, "explicit"):
            exceptions, _missing_why = load_verb_exceptions()
        # Assert
        assert "ls" in exceptions

    def test_pinned_tree_roots_the_noun_verb_custom_dict_too(
        self, elsewhere, tmp_path
    ):
        """§1c tags (`nouns:` / `*_verbs:`) follow the pin as well.

        `_audit._load_custom_dict` had its own copy of the cwd cascade;
        both copies had to move or `--path` would fix one rule family
        and not the other.
        """
        # Arrange
        tree = tmp_path / "with-nouns"
        tree.mkdir()
        _write_dict(tree, "nouns:\n  - bibentry\n")
        # Act
        with use_dict_root(tree, "explicit"):
            tags = load_custom_dict()
        # Assert
        assert tags.get("bibentry") == {"noun"}


# --------------------------------------------------------------------------- #
# POSITIVE CONTROL — the pin must not make the auditor blind                   #
# --------------------------------------------------------------------------- #


class TestPinnedTreeStillFindsRealViolations:
    """A correct pin still audits the pinned tree, findings and all."""

    @pytest.fixture
    def tree_with_undocumented_exception(self, tmp_path):
        """Pinned tree whose exemption lacks the mandatory `# why`."""
        tree = tmp_path / "sloppy"
        tree.mkdir()
        path = _write_dict(tree, "verb_exceptions:\n  - ls\n")
        return tree, path

    def test_real_violation_in_the_pinned_tree_is_still_reported(
        self, elsewhere, tree_with_undocumented_exception
    ):
        """§1f missing-`# why` fires — the pin narrows, it does not silence."""
        # Arrange
        tree, _path = tree_with_undocumented_exception
        out: list = []
        # Act
        with use_dict_root(tree, "explicit"):
            check_verb_exception_comments("demo", out)
        # Assert
        assert [v.rule for v in out] == ["§1f"]

    def test_the_finding_names_the_pinned_trees_dict_file(
        self, elsewhere, tree_with_undocumented_exception
    ):
        """The violation cites the PINNED file, not one under the cwd."""
        # Arrange
        tree, path = tree_with_undocumented_exception
        out: list = []
        # Act
        with use_dict_root(tree, "explicit"):
            check_verb_exception_comments("demo", out)
        # Assert
        assert str(path) in out[0].message


# --------------------------------------------------------------------------- #
# NAMING THE SUBJECT — the "which dict file did I read" line                   #
# --------------------------------------------------------------------------- #


class TestDictSourceIsAnnounced:
    """storage: this line alone would have saved the whole detour."""

    def test_report_names_the_pinned_file_and_the_rule_that_picked_it(
        self, elsewhere, pinned_tree
    ):
        """Same `via explicit` vocabulary as the resolved-tree banner."""
        # Arrange
        expected = (
            f"scitex-storage: cli-audit dict "
            f"{pinned_tree / '.scitex' / 'dev' / 'cli-audit-dict.yaml'} "
            f"(project, via explicit; read)"
        )
        # Act
        with use_dict_root(pinned_tree, "explicit"):
            lines = dict_source_report("scitex-storage")
        # Assert
        assert lines[0] == expected

    def test_absent_layers_are_reported_too(self, elsewhere):
        """"No dict was found at <path>" is the line you need most."""
        # Arrange (the fixture's cwd deliberately holds no dict)
        expected_suffix = "(project, via cwd; absent)"
        del elsewhere
        # Act
        lines = dict_source_report("scitex-storage")
        # Assert
        assert lines[0].endswith(expected_suffix)

    def test_project_root_equal_to_home_collapses_to_one_layer(self, elsewhere):
        """Deduped by resolved path — a double read would double findings."""
        # Arrange (the fixture sets HOME == cwd)
        del elsewhere
        # Act
        paths = dict_candidate_paths()
        # Assert
        assert len(paths) == 1
