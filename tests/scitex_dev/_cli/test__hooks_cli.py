"""Tests for ``scitex-dev hooks`` CLI — durable kill for the fanned-out
``run_lint.sh`` deploy class (Pillar 0 follow-up).

The 2026-06-12 ripple-wm dogfood pinned that operator projects each
carry a per-project copy of ``run_lint.sh`` that drifts independently.
Pillar 0 (#169) shipped the canonical hook inside scitex-dev at
``scitex_dev/_hooks/run_lint.sh``; this CLI is the durable kill —
install / update the canonical into a target project as a SYMLINK so
future scitex-dev releases auto-propagate.

Behaviour pinned here:
- ``install`` creates the deploy-path directory tree and the symlink
- ``install`` is idempotent (re-runs report ``up-to-date``)
- ``install`` refuses to clobber a non-symlink file (exit 1) without
  ``--force``; ``--force`` overwrites
- ``update`` re-points an existing symlink to the current bundled path
- ``list`` correctly reports ``ok`` / ``drift`` / ``stale`` / ``missing``
- ``path`` prints the absolute bundled path
"""

from __future__ import annotations

import os
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._hooks_cli import (
    KNOWN_HOOKS,
    register_hooks_commands,
)


@pytest.fixture
def cli():
    """Build a fresh top-level click group with hooks registered."""
    @click.group()
    def main():  # pragma: no cover - body is empty by design
        pass

    register_hooks_commands(main)
    return main


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------- #
# `hooks show-path` — bundled-path lookup                                #
# ---------------------------------------------------------------------- #


class TestHooksPath:
    """``hooks show-path <name>`` returns the absolute bundled-script path.

    Verb is ``show-path`` (compound-leaf form) NOT ``path`` per audit-cli
    §1 — a bare noun-typed leaf at the verb position is rejected as a §1
    violation. Was briefly ``print-path``; renamed again for §1f (`print`
    is a non-canonical synonym for the doctrine's `show` verb). The old
    name is exercised in ``test_print_path_alias_still_forwards`` below
    since it's still a working (deprecated) alias.
    """

    def test_prints_absolute_path_for_run_lint(self, cli, runner):
        # Arrange
        # (no fixtures needed; the cli fixture provides the wired runner.)
        # Act
        result = runner.invoke(cli, ["hooks", "show-path", "run_lint"])
        # Assert — single combined check: exit 0 AND output is the absolute
        # filesystem path of the bundled script (resolved + non-empty +
        # ends in run_lint.sh + matches the KNOWN_HOOKS source).
        source = KNOWN_HOOKS["run_lint"][0]
        emitted = (result.exit_code, result.output.strip())
        assert emitted == (0, source), (
            f"hooks show-path must echo the bundled-script path; got {emitted}"
        )

    def test_prints_absolute_path_for_run_testmon(self, cli, runner):
        # Arrange — run_testmon is the testmon warm-cache wrapper; repos
        # reference it via `entry: bash $(scitex-dev hooks show-path
        # run_testmon)` in .pre-commit-config.yaml, so show-path is the seam.
        # Act
        result = runner.invoke(cli, ["hooks", "show-path", "run_testmon"])
        # Assert — exit 0 AND output is the bundled run_testmon.sh path.
        source = KNOWN_HOOKS["run_testmon"][0]
        emitted = (
            result.exit_code,
            result.output.strip(),
            result.output.strip().endswith("run_testmon.sh"),
        )
        assert emitted == (0, source, True), (
            f"hooks show-path must echo the bundled run_testmon.sh path; "
            f"got {emitted}"
        )

    def test_print_path_alias_still_forwards(self, cli, runner):
        # Arrange — the OLD (deprecated) verb must still resolve the path
        # (existing `entry: bash $(scitex-dev hooks print-path ...)` lines
        # in downstream .pre-commit-config.yaml files must keep working).
        # Act
        result = runner.invoke(cli, ["hooks", "print-path", "run_lint"])
        # Assert — exit 0 and the bundled path is on stdout somewhere (the
        # once-per-shell deprecation warning goes to stderr, which
        # CliRunner may fold into .output, so check `in` not `==`).
        source = KNOWN_HOOKS["run_lint"][0]
        assert result.exit_code == 0 and source in result.output

    def test_show_path_json_emits_structured_object(self, cli, runner):
        # Arrange — --json (audit-cli §2 read-verb requirement) must emit
        # REAL structure, not just wrap the same string.
        import json

        # Act
        result = runner.invoke(cli, ["hooks", "show-path", "run_lint", "--json"])
        # Assert
        source = KNOWN_HOOKS["run_lint"][0]
        payload = json.loads(result.output)
        assert payload == {"name": "run_lint", "path": source}

    def test_show_path_default_output_stays_bare_path(self, cli, runner):
        # Arrange — command-substitution callers (`$(... show-path X)`)
        # must keep getting a bare path when --json is NOT passed.
        # Act
        result = runner.invoke(cli, ["hooks", "show-path", "run_lint"])
        # Assert
        source = KNOWN_HOOKS["run_lint"][0]
        assert result.output.strip() == source


# ---------------------------------------------------------------------- #
# `hooks install` — fresh install                                        #
# ---------------------------------------------------------------------- #


class TestHooksInstallFresh:
    """``hooks install`` creates the deploy tree + the symlink."""

    def test_creates_symlink_to_canonical_in_fresh_project(
        self, cli, runner, tmp_path
    ):
        # Arrange — empty target dir.
        project = tmp_path / "fresh-project"
        # Act
        result = runner.invoke(cli, ["hooks", "install", "--target", str(project)])
        # Assert — three invariants in one check: exit 0 AND target exists
        # AND it's a symlink resolving to the bundled canonical.
        source = KNOWN_HOOKS["run_lint"][0]
        deploy = project / "docs/to_claude/hooks/post-tool-use/run_lint.sh"
        emitted = (
            result.exit_code,
            deploy.is_symlink(),
            os.path.realpath(str(deploy)) if deploy.is_symlink() else None,
        )
        assert emitted == (0, True, os.path.realpath(source)), (
            f"fresh install must create canonical symlink; got {emitted}"
        )


# ---------------------------------------------------------------------- #
# Idempotency                                                            #
# ---------------------------------------------------------------------- #


class TestHooksInstallIdempotent:
    """Re-running ``hooks install`` reports ``up-to-date`` instead of clobbering."""

    def test_second_install_run_is_idempotent_noop(self, cli, runner, tmp_path):
        # Arrange — first install creates the symlink.
        project = tmp_path / "twice-installed-project"
        runner.invoke(cli, ["hooks", "install", "--target", str(project)])
        # Act — second invocation.
        result = runner.invoke(cli, ["hooks", "install", "--target", str(project)])
        # Assert — exit 0 AND output contains "up-to-date".
        emitted = (result.exit_code, "up-to-date" in result.output)
        assert emitted == (0, True), (
            f"re-install must be idempotent + announce up-to-date; got {emitted}"
        )


# ---------------------------------------------------------------------- #
# Refusal on real file                                                   #
# ---------------------------------------------------------------------- #


class TestHooksInstallRefusesNonSymlink:
    """Without ``--force``, install refuses to overwrite a real file."""

    def test_refuses_when_real_file_present_at_target(
        self, cli, runner, tmp_path
    ):
        # Arrange — pre-create a non-symlink file at the deploy path.
        project = tmp_path / "project-with-edit"
        deploy = project / "docs/to_claude/hooks/post-tool-use/run_lint.sh"
        deploy.parent.mkdir(parents=True)
        deploy.write_text("# operator-edited content\n")
        # Act
        result = runner.invoke(cli, ["hooks", "install", "--target", str(project)])
        # Assert — exit 1 AND the file content is still the operator's edit
        # (not clobbered) AND stderr mentions --force.
        emitted = (
            result.exit_code,
            deploy.read_text(),
            "--force" in (result.output + (result.stderr_bytes or b"").decode()),
        )
        assert emitted == (1, "# operator-edited content\n", True), (
            f"refusal must preserve user file + advertise --force; got {emitted}"
        )


# ---------------------------------------------------------------------- #
# Force overwrite                                                        #
# ---------------------------------------------------------------------- #


class TestHooksInstallForceOverwrites:
    """``--force`` replaces a real file with the canonical symlink."""

    def test_force_replaces_real_file_with_canonical_symlink(
        self, cli, runner, tmp_path
    ):
        # Arrange
        project = tmp_path / "project-being-forced"
        deploy = project / "docs/to_claude/hooks/post-tool-use/run_lint.sh"
        deploy.parent.mkdir(parents=True)
        deploy.write_text("# operator-edited content\n")
        # Act
        result = runner.invoke(
            cli, ["hooks", "install", "--target", str(project), "--force"]
        )
        # Assert
        source = KNOWN_HOOKS["run_lint"][0]
        emitted = (
            result.exit_code,
            deploy.is_symlink(),
            os.path.realpath(str(deploy)) if deploy.is_symlink() else None,
        )
        assert emitted == (0, True, os.path.realpath(source)), (
            f"--force must replace the real file with a canonical symlink; "
            f"got {emitted}"
        )


# ---------------------------------------------------------------------- #
# Update                                                                 #
# ---------------------------------------------------------------------- #


class TestHooksUpdateRelinks:
    """``hooks update`` repoints out-of-date symlinks to the current bundled path."""

    def test_update_relinks_stale_symlink_to_current_canonical(
        self, cli, runner, tmp_path
    ):
        # Arrange — pre-create a symlink to a DIFFERENT path so update
        # has something to re-point.
        project = tmp_path / "project-needing-update"
        deploy = project / "docs/to_claude/hooks/post-tool-use/run_lint.sh"
        deploy.parent.mkdir(parents=True)
        stale_target = tmp_path / "old-canonical-elsewhere"
        stale_target.write_text("# old\n")
        deploy.symlink_to(stale_target)
        # Act
        result = runner.invoke(cli, ["hooks", "update", "--target", str(project)])
        # Assert
        source = KNOWN_HOOKS["run_lint"][0]
        emitted = (
            result.exit_code,
            deploy.is_symlink(),
            os.path.realpath(str(deploy)),
        )
        assert emitted == (0, True, os.path.realpath(source)), (
            f"update must re-link to current canonical; got {emitted}"
        )


# ---------------------------------------------------------------------- #
# List                                                                   #
# ---------------------------------------------------------------------- #


class TestHooksListStatusReporting:
    """``hooks list`` correctly classifies installed / drift / missing."""

    def test_list_reports_ok_after_fresh_install(self, cli, runner, tmp_path):
        # Arrange
        project = tmp_path / "ok-project"
        runner.invoke(cli, ["hooks", "install", "--target", str(project)])
        # Act
        result = runner.invoke(cli, ["hooks", "list", "--target", str(project)])
        # Assert — single combined check on exit + presence of "ok" + hook name.
        emitted = (
            result.exit_code,
            "ok" in result.output,
            "run_lint" in result.output,
        )
        assert emitted == (0, True, True), (
            f"list must report ok after install; got {emitted}; "
            f"output={result.output!r}"
        )

    def test_list_reports_missing_when_target_has_no_hook(
        self, cli, runner, tmp_path
    ):
        # Arrange — project exists but no hooks installed.
        project = tmp_path / "empty-project"
        project.mkdir()
        # Act
        result = runner.invoke(cli, ["hooks", "list", "--target", str(project)])
        # Assert
        emitted = (
            result.exit_code,
            "missing" in result.output,
            "run_lint" in result.output,
        )
        assert emitted == (0, True, True), (
            f"list must report missing on empty project; got {emitted}; "
            f"output={result.output!r}"
        )

    def test_list_reports_drift_when_real_file_replaces_symlink(
        self, cli, runner, tmp_path
    ):
        # Arrange — operator edited the hook (it's no longer a symlink).
        project = tmp_path / "drifted-project"
        deploy = project / "docs/to_claude/hooks/post-tool-use/run_lint.sh"
        deploy.parent.mkdir(parents=True)
        deploy.write_text("# operator-edited content\n")
        # Act
        result = runner.invoke(cli, ["hooks", "list", "--target", str(project)])
        # Assert
        emitted = (
            result.exit_code,
            "drift" in result.output,
            "run_lint" in result.output,
        )
        assert emitted == (0, True, True), (
            f"list must report drift on non-symlink; got {emitted}; "
            f"output={result.output!r}"
        )
