"""Tests for ``scitex_dev._hooks`` — bundled canonical hook resolution.

Pins the testmon warm-cache wrapper (``run_testmon.sh``) added to make
pytest-testmon worktree-resilient: every release runs in a FRESH git
worktree (forced by the develop-pin hook) with a COLD ``.testmondata``,
so testmon re-runs the full ~2500-test suite instead of only impacted
tests. The wrapper seed-copies a persistent per-(repo, pyXY) cache in/out
of the worktree.

Behaviour pinned here:
- ``run_testmon_sh_path()`` returns an existing, executable, absolute
  path ending in ``run_testmon.sh``.
- ``run_testmon.sh --self-test`` exits 0 (cache-path resolution sanity).
- The wrapper SEEDS the worktree DB from the cache before pytest and
  WRITES the updated DB back to the cache after — verified end-to-end
  with a REAL shell stub standing in for python3/pytest (NO mocks,
  per PA-306).

The console-script shim (``run_testmon_cli``) has its own mirror suite in
``test_run_testmon_cli.py`` alongside its ``run_testmon_cli.py`` src module.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scitex_dev._hooks import run_testmon_sh_path


# ---------------------------------------------------------------------- #
# Path resolution                                                        #
# ---------------------------------------------------------------------- #


class TestRunTestmonShPath:
    """``run_testmon_sh_path()`` resolves the bundled, executable script."""

    def test_returns_existing_executable_run_testmon_sh(self):
        # Arrange
        # (no setup needed; the resolver reads bundled package state.)
        # Act
        path = run_testmon_sh_path()
        # Assert — single combined check: absolute AND exists AND executable
        # AND ends in run_testmon.sh.
        emitted = (
            os.path.isabs(path),
            os.path.isfile(path),
            os.access(path, os.X_OK),
            path.endswith("run_testmon.sh"),
        )
        assert emitted == (True, True, True, True), (
            f"run_testmon_sh_path must return an absolute, existing, "
            f"executable run_testmon.sh; got {path!r} -> {emitted}"
        )


# ---------------------------------------------------------------------- #
# Deterministic interpreter (NOT a bare `python3` off ambient $PATH)      #
# ---------------------------------------------------------------------- #
#
# PS-HOOK-001 bans a bare `python3` / `pytest` under a $PATH lookup. The
# wrapper itself used to commit that anti-pattern (`python3 -m pytest
# --testmon`). It now resolves an ABSOLUTE interpreter once up front
# (`$SCITEX_DEV_PYTHON` → `command -v python3`) and uses it everywhere,
# failing LOUDLY (exit 127) if none resolves.


class TestRunTestmonResolvedInterpreter:
    """The wrapper pins a resolved interpreter, not a bare `python3`."""

    def test_run_line_uses_resolved_var_not_bare_python3(self):
        # Arrange — locate the shipped wrapper source.
        script = run_testmon_sh_path()
        # Act — read its text.
        text = Path(script).read_text(encoding="utf-8")
        # Assert — the pytest RUN line goes through the resolved `$PY`
        # var, the resolver uses `command -v python3` captured to a var,
        # and NO bare `python3 -m pytest` remains.
        emitted = (
            '"$PY" -m pytest --testmon' in text,
            "command -v python3" in text,
            'PY="${SCITEX_DEV_PYTHON:-}"' in text,
            "python3 -m pytest" not in text,
        )
        assert emitted == (True, True, True, True), (
            f"run_testmon.sh must invoke a resolved interpreter, not a bare "
            f"`python3 -m pytest`; got {emitted}"
        )

    def test_exits_loudly_when_no_interpreter_resolvable(self, tmp_path):
        # Arrange — a sterile PATH with bash only (no python3) and no
        # SCITEX_DEV_PYTHON override, so the resolver cannot find any
        # interpreter and MUST fail closed rather than fall back to an
        # ambient tool.
        sterile = tmp_path / "sterile-bin"
        sterile.mkdir()
        real_bash = subprocess.run(
            ["bash", "-c", "command -v bash"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        (sterile / "bash").symlink_to(real_bash)
        env = {"PATH": str(sterile), "HOME": str(tmp_path), "LC_ALL": "C"}
        # Act — invoke via an absolute bash so exec resolution does not
        # itself depend on PATH; the wrapper's own `command -v python3`
        # then sees the sterile PATH.
        proc = subprocess.run(
            [real_bash, run_testmon_sh_path()],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env=env,
        )
        # Assert — exit 127 AND a clear "no python3" message (never a
        # silent skip that would let a cold suite pose as a warm run).
        combined = proc.stdout + proc.stderr
        emitted = (proc.returncode, "no python3 interpreter found" in combined)
        assert emitted == (127, True), (
            f"wrapper must fail loudly (127) when no interpreter resolves; "
            f"got {emitted}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )


# ---------------------------------------------------------------------- #
# Self-test                                                              #
# ---------------------------------------------------------------------- #


class TestRunTestmonSelfTest:
    """``run_testmon.sh --self-test`` exits 0 (cache-path sanity)."""

    def test_self_test_exits_zero(self):
        # Arrange
        script = run_testmon_sh_path()
        # Act
        proc = subprocess.run(
            ["bash", script, "--self-test"],
            capture_output=True,
            text=True,
        )
        # Assert — exit 0 AND the cache-key sanity line is present.
        emitted = (proc.returncode, "cache dir keyed by (repo, pyXY)" in proc.stdout)
        assert emitted == (0, True), (
            f"--self-test must exit 0 and report cache keying; got {emitted}; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


# ---------------------------------------------------------------------- #
# Behavioral: seed-in + write-back with a REAL shell stub (no mocks)     #
# ---------------------------------------------------------------------- #


_PY_STUB = """#!/usr/bin/env bash
# REAL fake python3 (NOT a mock): the wrapper calls `python3 -c <probe>`
# for the pyXY key and `python3 -m pytest --testmon ...` for the run.
# Delegate the probe to the real interpreter; for the pytest call, prove
# the seed by recording what the local DB held, then write a fresh DB so
# write-back has something to persist.
if [[ "$1" == "-c" ]]; then exec "{real_py}" "$@"; fi
if [[ "$1" == "-m" && "$2" == "pytest" ]]; then
  groot="$(git rev-parse --show-toplevel)"
  echo "SEEN_AT_RUN=$(cat "$groot/.testmondata" 2>/dev/null)" >&2
  echo "WRITTEN_BY_RUN" > "$groot/.testmondata"
  exit 0
fi
exec "{real_py}" "$@"
"""


def _make_worktree_and_stub(tmp_path):
    """Build a git worktree + a real python3 stub on a PATH dir. Returns
    (worktree, cache_root, stub_dir, pyxy)."""
    worktree = tmp_path / "wt"
    worktree.mkdir()
    subprocess.run(["git", "-C", str(worktree), "init", "-q"], check=True)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    stub = stub_dir / "python3"
    stub.write_text(_PY_STUB.format(real_py=sys.executable))
    stub.chmod(0o755)
    pyxy = f"py{sys.version_info.major}{sys.version_info.minor}"
    return worktree, cache_root, stub_dir, pyxy


def _run_wrapper(worktree, cache_root, stub_dir):
    env = dict(os.environ)
    env["SCITEX_TESTMON_CACHE_ROOT"] = str(cache_root)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", run_testmon_sh_path()],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )


class TestRunTestmonCacheRoundTrip:
    """The wrapper seeds the worktree from cache and writes the DB back."""

    def test_writes_db_back_to_cache_after_run(self, tmp_path):
        # Arrange — fresh worktree, empty cache.
        worktree, cache_root, stub_dir, pyxy = _make_worktree_and_stub(tmp_path)
        repo = worktree.name
        cache_file = cache_root / repo / pyxy / ".testmondata"
        # Act
        proc = _run_wrapper(worktree, cache_root, stub_dir)
        # Assert — exit 0 AND the cache now holds the DB the run produced.
        emitted = (
            proc.returncode,
            cache_file.is_file(),
            cache_file.read_text().strip() if cache_file.is_file() else None,
        )
        assert emitted == (0, True, "WRITTEN_BY_RUN"), (
            f"wrapper must persist the post-run DB to the cache; got {emitted}; "
            f"stderr={proc.stderr!r}"
        )

    def test_seeds_worktree_from_cache_before_run(self, tmp_path):
        # Arrange — pre-warm the cache so seed-in has something to copy.
        worktree, cache_root, stub_dir, pyxy = _make_worktree_and_stub(tmp_path)
        repo = worktree.name
        cache_dir = cache_root / repo / pyxy
        cache_dir.mkdir(parents=True)
        (cache_dir / ".testmondata").write_text("WARM_SEED")
        # Act
        proc = _run_wrapper(worktree, cache_root, stub_dir)
        # Assert — the stub reported the seeded DB content was present at run
        # time (proves SEED-IN copied the warm cache into the worktree).
        emitted = (proc.returncode, "SEEN_AT_RUN=WARM_SEED" in proc.stderr)
        assert emitted == (0, True), (
            f"wrapper must seed the worktree DB from the warm cache; got "
            f"{emitted}; stderr={proc.stderr!r}"
        )
