"""Tests for ``scitex-dev hooks enable-pre-push`` and the bundled
pre-push hook script.

Pins the structural improvement from 2026-06-15: a local pre-push
gate that runs scitex-dev's audit + scope tests BEFORE ``git push``
so the "push → CI red → push fix → CI red again" merry-go-round
stops. The gate is distributable across the ecosystem via the same
symlink mechanism as ``run_lint``.

Behaviour pinned here:
- ``enable-pre-push`` symlinks the bundled ``pre-push.sh`` into
  ``<target>/.githooks/pre-push`` (no ``.sh`` suffix — git's pre-push
  contract is filename-based).
- ``enable-pre-push`` runs ``git -C <target> config core.hooksPath
  .githooks`` so the symlink actually fires.
- ``--dry-run`` reports both actions without touching the filesystem
  or git config.
- ``--force`` is required to overwrite a real (non-symlink) hook.
- The bundled script passes its own ``--self-test`` (sanity check
  that the script parses and the required binaries are detectable).
- The script honours ``SCITEX_DEV_SKIP_PREPUSH=1`` and exits 0 with
  a notice (operator emergency hatch).
"""

from __future__ import annotations

import os
import stat
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
    ``git -C <target> config core.hooksPath .githooks`` which only
    works inside a git repo. We deliberately use ``--initial-branch``
    so the test doesn't depend on the host's ``init.defaultBranch``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    # A user.email / user.name is not required for `git config`, but
    # `git init` itself sometimes warns; we don't care about warnings.
    return repo


# ---------------------------------------------------------------------- #
# Registry: pre_push is a KNOWN_HOOK                                     #
# ---------------------------------------------------------------------- #


class TestPrePushRegistered:
    """``pre_push`` is registered with the canonical deploy path."""

    def test_pre_push_in_known_hooks_with_dot_githooks_deploy_path(self):
        # Arrange — KNOWN_HOOKS is the registry under test.
        entry = KNOWN_HOOKS.get("pre_push")
        # Assert — entry exists, source is the bundled file, deploy is
        # `.githooks/pre-push` (the git-recognised filename, NO `.sh`).
        emitted = (
            entry is not None,
            entry and entry[0] == pre_push_sh_path(),
            entry and entry[1] == ".githooks/pre-push",
        )
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
        # Read back the git config from the same repo.
        config_rc = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        )
        # Assert — five invariants in one check:
        # exit 0 AND symlink exists AND points at the bundled canonical
        # AND core.hooksPath is set to .githooks AND output mentions
        # both actions.
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
        # Act
        result = runner.invoke(
            cli, ["hooks", "enable-pre-push", "--target", str(fresh_git_repo)]
        )
        # Assert — exit 0 AND output announces up-to-date for the git
        # config side (the symlink side already does via "up-to-date").
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
        # Read post-state.
        post_config = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        deploy = fresh_git_repo / ".githooks" / "pre-push"
        # Assert — exit 0 AND no symlink created AND config unchanged
        # AND output uses "would install" / "would configure" prose.
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
        # Assert — exit 1 AND the operator's file content survives AND
        # the user is told about --force.
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
# Bundled script self-test                                               #
# ---------------------------------------------------------------------- #


class TestPrePushScriptSelfTest:
    """The shipped ``pre-push.sh`` parses and self-tests cleanly."""

    def test_bundled_script_passes_self_test(self):
        # Arrange — the bundled script ships executable; verify the
        # bit is set (else git won't run it).
        path = Path(pre_push_sh_path())
        mode = path.stat().st_mode
        is_exec = bool(mode & stat.S_IXUSR)
        # Act — run --self-test under a 5s budget.
        proc = subprocess.run(
            ["bash", str(path), "--self-test"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Assert — script exists, executable, self-test exits 0 AND
        # mentions "PASS" (a sanity-check assertion ran).
        emitted = (
            path.exists(),
            is_exec,
            proc.returncode,
            "PASS" in proc.stdout,
        )
        assert emitted == (True, True, 0, True), (
            f"pre-push.sh --self-test must succeed; got {emitted}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )

    def test_skip_env_var_short_circuits_to_exit_zero(self, tmp_path):
        # Arrange — invoke the live hook (not --self-test) with the
        # bypass env var set. Run inside a real git repo so the
        # `git rev-parse --show-toplevel` probe doesn't bail first.
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        env = {**os.environ, "SCITEX_DEV_SKIP_PREPUSH": "1"}
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit 0 AND stderr mentions the bypass for transcript
        # visibility.
        emitted = (proc.returncode, "SCITEX_DEV_SKIP_PREPUSH" in proc.stderr)
        assert emitted == (0, True), (
            f"SKIP env var must short-circuit cleanly; got {emitted}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
