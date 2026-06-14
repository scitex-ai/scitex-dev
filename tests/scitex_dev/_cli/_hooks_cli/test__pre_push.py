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
        # Arrange — operator has already configured core.hooksPath
        # to a custom dir (e.g. they prefer `.hooks` or share a
        # team-wide hooks repo).
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
        # Read the git config post-call — must be unchanged.
        post = subprocess.run(
            ["git", "-C", str(fresh_git_repo), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        combined = result.output + (result.stderr_bytes or b"").decode()
        # Assert — exit 1 AND the operator's config survives AND the
        # error names BOTH the previous value AND --force as the override.
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
        # "forced" verb appears with the previous value (transcript
        # record of what changed).
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


# ---------------------------------------------------------------------- #
# Q2 — 3-tier python entrypoint fallback in the hook script              #
# ---------------------------------------------------------------------- #
#
# Operator answer 2026-06-15: when `scitex-dev` is missing from PATH
# (editable-install drift: the .pth points at a removed worktree), the
# hook MUST surface the literal remediation `uv pip install -e
# <checkout>` and exit non-zero. NO silent skip — CI would have caught
# the same import error, just slower.


class TestPrePushPythonFallback:
    """Bundled ``pre-push.sh`` 3-tier-probes the scitex-dev entrypoint."""

    def test_loud_error_when_all_three_probes_fail(self, tmp_path):
        # Arrange — invoke the live hook (not --self-test) with PATH
        # scrubbed of every probe target: scitex-dev, python3, python.
        # The script must surface the actionable remediation, not
        # silently SKIP the audit step.
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        # Build a sterile PATH: just /bin + /usr/bin minus python*,
        # minus scitex-dev. We accomplish this by building a tmp
        # PATH-bin dir containing ONLY git + bash + (basic shell utils
        # the hook needs) and pointing PATH at it. timeout(1) is
        # invoked by the hook so we include coreutils' timeout too.
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        # Symlink ONLY the binaries the hook needs to reach the
        # python-probe step. NB: we DELIBERATELY omit python3 / python
        # / scitex-dev so all three probes fail.
        needed = ["bash", "git", "timeout", "basename", "dirname", "command"]
        for bin_name in needed:
            real = subprocess.run(
                ["bash", "-c", f"command -v {bin_name}"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if real and Path(real).exists():
                (sterile / bin_name).symlink_to(real)
        env = {
            "PATH": str(sterile),
            "HOME": str(tmp_path),
            "LC_ALL": "C",
        }
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit non-zero AND the actionable remediation
        # string appears AND the three probes are named.
        combined = proc.stdout + proc.stderr
        emitted = (
            proc.returncode != 0,
            "not importable" in combined,
            "uv pip install -e" in combined,
            "scitex-dev-checkout" in combined or "<scitex-dev-checkout>" in combined,
        )
        assert emitted == (True, True, True, True), (
            f"hook must surface remediation when all probes fail; got "
            f"{emitted}\nrc={proc.returncode}\nstdout={proc.stdout!r}\n"
            f"stderr={proc.stderr!r}"
        )

    def test_python_module_fallback_used_when_scitex_dev_missing(self, tmp_path):
        # Arrange — PATH has python3 (which CAN import scitex_dev in
        # this venv) but no `scitex-dev` script. The hook must fall
        # through tier 1 → tier 2 successfully and run audit-all via
        # `python3 -m scitex_dev`.
        import sys

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        needed = ["bash", "git", "timeout", "basename", "dirname"]
        for bin_name in needed:
            real = subprocess.run(
                ["bash", "-c", f"command -v {bin_name}"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if real and Path(real).exists():
                (sterile / bin_name).symlink_to(real)
        # Provide a `python3` wrapper in the sterile dir that execs
        # the CURRENT interpreter (`sys.executable`). We can't simply
        # symlink to `sys.executable`: when the active venv's python
        # is itself a symlink to /usr/local/bin/python, Python uses
        # the symlink-following argv[0] heuristic to find
        # `pyvenv.cfg`, which would NOT be present at the symlink
        # target — so `import scitex_dev` would fail. A thin shell
        # wrapper preserves the venv-bin path so site.py walks the
        # venv's `__editable__.scitex_dev*.pth` correctly.
        wrapper = sterile / "python3"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
        env = {
            "PATH": str(sterile),
            "HOME": str(tmp_path),
            "LC_ALL": "C",
            # Don't inherit a SCITEX_DEV_PREPUSH_TIMEOUT that might be
            # too short; the audit step takes a few seconds.
            "SCITEX_DEV_PREPUSH_TIMEOUT": "60",
        }
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(repo),
            env=env,
        )
        # Assert — the hook MUST NOT hit the loud-error remediation
        # path; it MUST have chosen the python3 -m fallback (visible
        # in the `[1/2] ...` echo). We don't assert exit code (the
        # tmp repo has no pyproject.toml so audit-all may itself
        # complain), only that the fallback PROBE picked tier 2.
        combined = proc.stdout + proc.stderr
        emitted = (
            "python3 -m scitex_dev" in combined,
            "not importable" not in combined,
            "Editable install may have drifted" not in combined,
        )
        assert emitted == (True, True, True), (
            f"hook must use `python3 -m scitex_dev` fallback when "
            f"scitex-dev is off PATH; got {emitted}\nstdout={proc.stdout!r}\n"
            f"stderr={proc.stderr!r}"
        )


# ---------------------------------------------------------------------- #
# Regression — capture audit-all rc correctly                            #
# ---------------------------------------------------------------------- #
#
# 2026-06-15 E2E push test surfaced that the live hook reported
# `audit-all failed (rc=0)` AND let the push through even when audit-all
# itself returned 1. Root cause: `if ! cmd; then echo "$?"` — bash sets
# `$?` to 0 (the inverted truthy value) inside the `then` branch, so
# the original exit code was always lost. The hook must capture `$?`
# directly after the command, NOT inside an `if ! ...; then` block.


class TestPrePushAuditRcPropagation:
    """The hook surfaces the REAL audit-all rc and blocks the push on non-zero."""

    def test_nonzero_audit_rc_blocks_push_and_names_the_rc(self, tmp_path):
        # Arrange — stub `scitex-dev` with a script that returns rc=2
        # AND emits a recognisable token so we know the stub fired.
        # The hook must:
        #   * exit non-zero (push BLOCKED)
        #   * print the rc=2 (NOT rc=0) in the failure message
        # The bash `if ! cmd; then $?` idiom would print rc=0 here —
        # that's exactly the regression we're pinning.
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        needed = ["bash", "git", "timeout", "basename", "dirname"]
        for bin_name in needed:
            real = subprocess.run(
                ["bash", "-c", f"command -v {bin_name}"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if real and Path(real).exists():
                (sterile / bin_name).symlink_to(real)
        # Stub scitex-dev: succeed on the `--version` probe (tier-1
        # detection), exit 2 on the actual `ecosystem audit-all ...`
        # call. The stub emits a recognisable marker so we know it
        # fired (defence-in-depth — keeps the test from passing for
        # the wrong reason if PATH didn't pick it up).
        stub = sterile / "scitex-dev"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then\n'
            '    echo "scitex-dev 99.99.99 (stub)"\n'
            "    exit 0\n"
            "fi\n"
            'echo "[STUB scitex-dev] argv: $*" >&2\n'
            "exit 2\n"
        )
        stub.chmod(0o755)
        env = {
            "PATH": str(sterile),
            "HOME": str(tmp_path),
            "LC_ALL": "C",
            "SCITEX_DEV_PREPUSH_TIMEOUT": "10",
        }
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit non-zero AND failure message names rc=2 (NOT
        # rc=0 — the `if !` bash trap). Also assert the stub really
        # fired (defence-in-depth: a path issue could make this test
        # pass for the wrong reason).
        combined = proc.stdout + proc.stderr
        emitted = (
            proc.returncode != 0,
            "[STUB scitex-dev]" in combined,
            "rc=2" in combined,
            "rc=0" not in combined,
            "PUSH BLOCKED" in combined,
        )
        assert emitted == (True, True, True, True, True), (
            f"hook must propagate audit-all rc verbatim; got {emitted}\n"
            f"rc={proc.returncode}\nstdout={proc.stdout!r}\n"
            f"stderr={proc.stderr!r}"
        )
