"""Tests for ``scitex-dev hooks enable-pre-push`` (the CLI command).

Pins the structural improvement from 2026-06-15: a local pre-push gate
that runs scitex-dev's audit + scope tests BEFORE ``git push`` so the
"push → CI red → push fix → CI red again" merry-go-round stops. The gate
is distributable across the ecosystem via the same symlink mechanism as
``run_lint``.

Behaviour pinned here (CLI half — see
``tests/scitex_dev/_hooks/test___init___pre_push.py`` for the
bundled-script half):
- ``pre_push`` is a KNOWN_HOOK deploying to ``.githooks/pre-push``.
- ``enable-pre-push`` symlinks the bundled ``pre-push.sh`` into
  ``<target>/.githooks/pre-push`` (no ``.sh`` suffix — git's pre-push
  contract is filename-based).
- ``enable-pre-push`` runs ``git -C <target> config core.hooksPath
  .githooks`` so the symlink actually fires.
- ``--dry-run`` reports both actions without touching FS or git config.
- ``--force`` is required to overwrite a real (non-symlink) hook.
- ``core.hooksPath`` is additive-then-refuse (Q1 semantics).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._hooks_cli import KNOWN_HOOKS, register_hooks_commands
from scitex_dev._hooks import pre_push_sh_path


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


@pytest.fixture
def fresh_git_repo(tmp_path: Path) -> Path:
    """Initialise an empty git repo at ``tmp_path/repo``.

    Required for ``enable-pre-push`` because it runs
    ``git -C <target> config core.hooksPath .githooks`` which only works
    inside a git repo. We use ``--initial-branch`` so the test doesn't
    depend on the host's ``init.defaultBranch``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    return repo


# ---------------------------------------------------------------------- #
# Registry: pre_push is a KNOWN_HOOK                                     #
# ---------------------------------------------------------------------- #


class TestPrePushRegistered:
    """``pre_push`` is registered with the canonical deploy path."""

    def test_pre_push_in_known_hooks_with_dot_githooks_deploy_path(self):
        # Arrange — KNOWN_HOOKS is the registry under test.
        entry = KNOWN_HOOKS.get("pre_push")
        # Act — read the registered tuple.
        source_ok = entry and entry[0] == pre_push_sh_path()
        deploy_ok = entry and entry[1] == ".githooks/pre-push"
        # Assert — entry exists, source is the bundled file, deploy is
        # `.githooks/pre-push` (the git-recognised filename, NO `.sh`).
        emitted = (entry is not None, source_ok, deploy_ok)
        assert emitted == (True, True, True), (
            f"pre_push must register as bundled→.githooks/pre-push; got {emitted}"
        )


# ---------------------------------------------------------------------- #
# `hooks enable-pre-push` happy path                                     #
# ---------------------------------------------------------------------- #


class TestEnablePrePushFresh:
    """``enable-pre-push`` symlinks the gate AND wires core.hooksPath."""

    def test_creates_symlink_and_configures_core_hookspath(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — fresh git repo without any hooks installed.
        deploy = fresh_git_repo / ".githooks" / "pre-push"
        # Act
        result = runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        config_rc = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        )
        # Assert — exit 0 AND symlink exists AND points at the bundled
        # canonical AND core.hooksPath is .githooks AND output names both.
        emitted = (
            result.exit_code,
            deploy.is_symlink(),
            os.path.realpath(str(deploy)) if deploy.is_symlink() else None,
            config_rc.stdout.strip(),
            "pre_push" in result.output and "core.hooksPath" in result.output,
        )
        assert emitted == (
            0,
            True,
            os.path.realpath(pre_push_sh_path()),
            ".githooks",
            True,
        ), (
            f"enable-pre-push must symlink + wire core.hooksPath; got "
            f"{emitted}\noutput={result.output!r}"
        )


# ---------------------------------------------------------------------- #
# Idempotency                                                            #
# ---------------------------------------------------------------------- #


class TestEnablePrePushIdempotent:
    """Re-running ``enable-pre-push`` is a no-op."""

    def test_second_run_reports_up_to_date_no_changes(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — first run wires everything.
        runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        # Act — run it a second time.
        result = runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        # Assert — exit 0 AND output announces up-to-date.
        emitted = (result.exit_code, "up-to-date" in result.output)
        assert emitted == (0, True), (
            f"re-run must be idempotent + announce up-to-date; got "
            f"{emitted}\noutput={result.output!r}"
        )


# ---------------------------------------------------------------------- #
# Dry-run                                                                #
# ---------------------------------------------------------------------- #


class TestEnablePrePushDryRun:
    """``--dry-run`` plans the actions without touching the filesystem."""

    def test_dry_run_does_not_create_symlink_or_set_config(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — capture the pre-state of the git config (unset).
        pre_config = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        # Act
        result = runner.invoke(
            cli,
            [
                "hooks",
                "enable-pre-push",
                "--target",
                str(fresh_git_repo),
                "--dry-run",
            ],
        )
        post_config = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        deploy = fresh_git_repo / ".githooks" / "pre-push"
        # Assert — exit 0 AND no symlink AND config unchanged AND output
        # uses "would install" / "would configure" prose.
        emitted = (
            result.exit_code,
            deploy.exists() or deploy.is_symlink(),
            pre_config == post_config,
            "would install" in result.output and "would configure" in result.output,
        )
        assert emitted == (0, False, True, True), (
            f"--dry-run must not touch FS or git config; got {emitted}\n"
            f"output={result.output!r}"
        )


# ---------------------------------------------------------------------- #
# Refusal on real file                                                   #
# ---------------------------------------------------------------------- #


class TestEnablePrePushRefusesRealFile:
    """Without ``--force``, ``enable-pre-push`` refuses a pre-existing real file."""

    def test_refuses_when_real_file_present_at_deploy_path(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — pre-create a non-symlink file at the deploy path.
        deploy = fresh_git_repo / ".githooks" / "pre-push"
        deploy.parent.mkdir(parents=True)
        deploy.write_text("#!/bin/sh\n# operator-edited pre-push hook\n")
        # Act
        result = runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        # Assert — exit 1 AND the operator's file survives AND --force
        # is advertised.
        emitted = (
            result.exit_code,
            deploy.read_text(),
            "--force" in (result.output + (result.stderr_bytes or b"").decode()),
        )
        assert emitted == (
            1,
            "#!/bin/sh\n# operator-edited pre-push hook\n",
            True,
        ), f"refusal must preserve operator file + advertise --force; got {emitted}"


# ---------------------------------------------------------------------- #
# Q1 — additive-then-refuse semantics for core.hooksPath                 #
# ---------------------------------------------------------------------- #
#
# Operator answer 2026-06-15: when `core.hooksPath` is already set to
# something OTHER than `.githooks`, do NOT silently clobber it. Refuse
# with a clear remediation message; `--force` overrides. Idempotent on
# `.githooks` (the bundled hook co-exists with run_lint in the SAME dir
# — Pillar 0 anti-drift).


class TestEnablePrePushHooksPathSemantics:
    """``enable-pre-push`` is additive-then-refuse on ``core.hooksPath``."""

    def test_refuses_to_overwrite_existing_non_dot_githooks_value(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — operator already configured a custom core.hooksPath.
        subprocess.run(
            [
                "git",
                "-C",
                str(fresh_git_repo),
                "config",
                "core.hooksPath",
                ".custom-hooks",
            ],
            check=True,
            capture_output=True,
        )
        # Act — without --force.
        result = runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        post = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        combined = result.output + (result.stderr_bytes or b"").decode()
        # Assert — exit 1 AND the operator's config survives AND the error
        # names BOTH the previous value AND --force.
        emitted = (
            result.exit_code,
            post,
            "refused" in combined.lower(),
            ".custom-hooks" in combined,
            "--force" in combined,
        )
        assert emitted == (1, ".custom-hooks", True, True, True), (
            f"refuse-elsewhere must preserve config + advertise --force; "
            f"got {emitted}\noutput={combined!r}"
        )

    def test_force_overwrites_existing_non_dot_githooks_value(
        self, cli, runner, fresh_git_repo
    ):
        # Arrange — operator has core.hooksPath = .custom-hooks.
        subprocess.run(
            [
                "git",
                "-C",
                str(fresh_git_repo),
                "config",
                "core.hooksPath",
                ".custom-hooks",
            ],
            check=True,
            capture_output=True,
        )
        # Act — with --force.
        result = runner.invoke(
            cli,
            [
                "hooks",
                "enable-pre-push",
                "--target",
                str(fresh_git_repo),
                "--force",
            ],
        )
        post = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        # Assert — exit 0 AND core.hooksPath = .githooks now AND the
        # "forced" verb appears with the previous value.
        emitted = (
            result.exit_code,
            post,
            "forced" in result.output,
            ".custom-hooks" in result.output,
        )
        assert emitted == (0, ".githooks", True, True), (
            f"--force must overwrite + log previous value; got {emitted}\n"
            f"output={result.output!r}"
        )
