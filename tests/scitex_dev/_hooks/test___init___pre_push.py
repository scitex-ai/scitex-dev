"""Tests for the bundled ``scitex_dev/_hooks/pre-push.sh`` gate script.

Named ``test___init___pre_push.py``, not ``test_pre_push.py``: the script
under test is a ``.sh``, so the only Python module this suite has to mirror
is ``_hooks/__init__.py`` — which is what it imports (``pre_push_sh_path``).
``_pre_push`` is the PS-204 descriptor suffix distinguishing it from
``test___init__.py`` (the run_testmon half of the same module).

Companion to ``tests/scitex_dev/_cli/_hooks_cli/test__pre_push.py`` (the
CLI half). This half drives the shipped shell script directly:

- The script ships executable and passes its own ``--self-test``.
- It honours ``SCITEX_DEV_SKIP_PREPUSH=1`` (operator emergency hatch).
- It 3-tier-probes the scitex-dev entrypoint (scitex-dev / python3 -m /
  python -m) and surfaces a loud ``uv pip install -e`` remediation when
  all three fail (editable-install drift), never a silent skip.
- REGRESSION: it captures the REAL audit-all rc and BLOCKS the push on
  non-zero — the ``if ! cmd; then $?`` bash idiom zeroes the exit code,
  reporting success on a failed check. This is the bug #196 fixed.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from scitex_dev._hooks import pre_push_sh_path
from tests._child_env import with_loader_path


# ---------------------------------------------------------------------- #
# Bundled script self-test                                               #
# ---------------------------------------------------------------------- #


class TestPrePushScriptSelfTest:
    """The shipped ``pre-push.sh`` parses and self-tests cleanly."""

    def test_bundled_script_passes_self_test(self):
        # Arrange — the bundled script ships executable; verify the bit
        # is set (else git won't run it).
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
        # bypass env var set, inside a real git repo so the
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
# 3-tier python entrypoint fallback in the hook script                   #
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
        # Arrange — invoke the live hook with PATH scrubbed of every
        # probe target (scitex-dev, python3, python) so all three fail
        # and the script must surface the actionable remediation.
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        # Symlink ONLY the binaries the hook needs to reach the
        # python-probe step. We DELIBERATELY omit python3 / python /
        # scitex-dev so all three probes fail.
        needed = ["bash", "git", "timeout", "basename", "dirname", "command"]
        for bin_name in needed:
            real = subprocess.run(
                ["bash", "-c", f"command -v {bin_name}"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if real and Path(real).exists():
                (sterile / bin_name).symlink_to(real)
        # Sterile by design — the omissions above ARE the experiment. The
        # loader path is not one of them; see tests/_child_env.py.
        env = with_loader_path(
            {
                "PATH": str(sterile),
                "HOME": str(tmp_path),
                "LC_ALL": "C",
            }
        )
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit non-zero AND the actionable remediation string
        # appears AND the three probes are named.
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
        # Arrange — PATH has python3 (which CAN import scitex_dev in this
        # venv) but no `scitex-dev` script. The hook must fall through
        # tier 1 → tier 2 and run audit-all via `python3 -m scitex_dev`.
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
        # A thin `python3` wrapper execs the CURRENT interpreter
        # (`sys.executable`) so site.py walks the venv's editable .pth
        # correctly (a bare symlink to sys.executable can lose pyvenv.cfg
        # resolution).
        wrapper = sterile / "python3"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        wrapper.chmod(0o755)
        # The `python3` wrapper above execs `sys.executable`, so the child
        # is a real interpreter and needs the loader path to start at all
        # — without it tier 2 cannot be reached and the probe reports a
        # tier choice that was never made. See tests/_child_env.py.
        env = with_loader_path(
            {
                "PATH": str(sterile),
                "HOME": str(tmp_path),
                "LC_ALL": "C",
                "SCITEX_DEV_PREPUSH_TIMEOUT": "60",
            }
        )
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(repo),
            env=env,
        )
        # Assert — the hook MUST NOT hit the loud-error remediation path;
        # it MUST have chosen the python3 -m fallback. We don't assert the
        # exit code (the tmp repo has no pyproject.toml so audit-all may
        # itself complain), only that the PROBE picked tier 2.
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
# REGRESSION — capture audit-all rc correctly (the #196 bugfix)          #
# ---------------------------------------------------------------------- #
#
# 2026-06-15 E2E push test surfaced that the live hook reported
# `audit-all failed (rc=0)` AND let the push through even when audit-all
# itself returned 1. Root cause: `if ! cmd; then echo "$?"` — bash sets
# `$?` to 0 (the inverted truthy value) inside the `then` branch, so the
# original exit code was always lost. The hook must capture `$?` directly
# after the command, NOT inside an `if ! ...; then` block.


class TestPrePushAuditRcPropagation:
    """The hook surfaces the REAL audit-all rc and blocks the push on non-zero."""

    def test_nonzero_audit_rc_blocks_push_and_names_the_rc(self, tmp_path):
        # Arrange — stub `scitex-dev` so the `--version` probe succeeds
        # (tier-1 detection) but the actual `ecosystem audit-all` call
        # exits 2 with a recognisable marker. The `if ! cmd; then $?`
        # idiom would print rc=0 here — that's the regression we pin.
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
        # Sterile by design; the loader path is exempt (tests/_child_env.py).
        env = with_loader_path(
            {
                "PATH": str(sterile),
                "HOME": str(tmp_path),
                "LC_ALL": "C",
                "SCITEX_DEV_PREPUSH_TIMEOUT": "10",
            }
        )
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit non-zero AND failure message names rc=2 (NOT rc=0
        # — the `if !` bash trap) AND the stub really fired AND the push
        # is reported BLOCKED.
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


# ---------------------------------------------------------------------- #
# Step 4 routes through the run_testmon warm-cache wrapper                #
# ---------------------------------------------------------------------- #
#
# Step 4 must NOT run a bare `pytest --testmon`; it must resolve and call
# the canonical `run_testmon.sh` warm-cache wrapper (via `scitex-dev hooks
# show-path run_testmon`) so a FRESH release worktree gets the persistent
# `.testmondata` cache instead of a cold full-suite run. And the wrapper's
# rc MUST propagate — a failing testmon run blocks the push (the same
# `if ! cmd` rc-zeroing trap the audit step avoids).


def _link_needed_bins(sterile: Path, names: list[str]) -> None:
    """Symlink each real binary in ``names`` into ``sterile``."""
    for bin_name in names:
        real = subprocess.run(
            ["bash", "-c", f"command -v {bin_name}"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if real and Path(real).exists():
            (sterile / bin_name).symlink_to(real)


class TestPrePushStep4RoutesThroughWrapper:
    """Step 4 calls the run_testmon wrapper and propagates its rc."""

    def test_step4_source_calls_wrapper_not_bare_pytest(self):
        # Arrange — locate the shipped pre-push gate source.
        script = Path(pre_push_sh_path())
        # Act — read its text.
        text = script.read_text(encoding="utf-8")
        # Assert — Step 4 resolves the wrapper via `hooks show-path
        # run_testmon` and invokes it as `bash "$RUN_TESTMON"`, and the
        # old bare `$PYTEST_BIN --testmon` invocation is gone.
        emitted = (
            "hooks show-path run_testmon" in text,
            'bash "$RUN_TESTMON"' in text,
            "$PYTEST_BIN" not in text,
        )
        assert emitted == (True, True, True), (
            f"pre-push Step 4 must route through the run_testmon wrapper, "
            f"not a bare pytest; got {emitted}"
        )

    def test_failing_wrapper_blocks_push_and_names_the_rc(self, tmp_path):
        # Arrange — a stub `scitex-dev` whose `--version` + `audit-all`
        # succeed (so the gate reaches Step 4) and whose `hooks show-path
        # run_testmon` returns a stub wrapper that exits 1 (a failing
        # testmon run). tests/ must exist for Step 4 to fire.
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "tests").mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(repo)],
            check=True,
            capture_output=True,
        )
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        _link_needed_bins(
            sterile,
            ["bash", "git", "timeout", "basename", "dirname", "cat", "sh"],
        )
        wrapper = sterile / "stub_run_testmon.sh"
        wrapper.write_text(
            "#!/bin/sh\n"
            'echo "[STUB run_testmon] argv: $*" >&2\n'
            "exit 1\n"
        )
        wrapper.chmod(0o755)
        stub = sterile / "scitex-dev"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then\n'
            '    echo "scitex-dev 99.99.99 (stub)"\n'
            "    exit 0\n"
            "fi\n"
            'if [ "$1" = "ecosystem" ] && [ "$2" = "audit-all" ]; then\n'
            "    exit 0\n"
            "fi\n"
            'if [ "$1" = "hooks" ] && [ "$2" = "show-path" ] '
            '&& [ "$3" = "run_testmon" ]; then\n'
            f'    echo "{wrapper}"\n'
            "    exit 0\n"
            "fi\n"
            "exit 1\n"
        )
        stub.chmod(0o755)
        # Sterile by design; the loader path is exempt (tests/_child_env.py).
        env = with_loader_path(
            {
                "PATH": str(sterile),
                "HOME": str(tmp_path),
                "LC_ALL": "C",
                "SCITEX_DEV_PREPUSH_TIMEOUT": "10",
            }
        )
        # Act
        proc = subprocess.run(
            ["bash", pre_push_sh_path()],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(repo),
            env=env,
        )
        # Assert — exit non-zero AND the stub wrapper actually fired
        # (proves routing) AND the real rc=1 is named (NOT the inverted
        # 0) AND the push is BLOCKED naming the scope-test failure.
        combined = proc.stdout + proc.stderr
        emitted = (
            proc.returncode != 0,
            "[STUB run_testmon]" in combined,
            "scope tests failed (rc=1)" in combined,
            "scope tests returned 1" in combined,
            "PUSH BLOCKED" in combined,
        )
        assert emitted == (True, True, True, True, True), (
            f"failing wrapper must block the push and name rc=1; got "
            f"{emitted}\nrc={proc.returncode}\nstdout={proc.stdout!r}\n"
            f"stderr={proc.stderr!r}"
        )
