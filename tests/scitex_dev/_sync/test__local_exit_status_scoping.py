#!/usr/bin/env python3
"""The sync command chain must not swallow a failing step's exit status.

WHY THIS TEST EXISTS (measured 2026-08-04, scitex-logging's spartan host):
`_build_sync_commands` returns a list the caller joins with `" && "` into ONE
remote shell string. A trailing `|| true` — written to make `stash pop`
non-fatal — binds to the WHOLE preceding `&&` chain, not to the command in
front of it. So a pull that died on a stale `.git/index.lock` short-circuited
the chain, `|| true` forced exit 0, and the caller reported
`{"status": "ok", "output": ""}` for a host that never synced. Two weeks of
staleness behind a green result.

These tests run the ACTUAL joined string through a real shell rather than
asserting on its text, because the defect was in shell semantics, not in the
wording — a text assertion would have passed against the broken version just as
readily as the fixed one.
"""

import subprocess

from scitex_dev._sync._local import _build_sync_commands


class _Host:
    """Minimal stand-in for HostConfig (only the two fields used here)."""

    remote_base = "/tmp"
    pip_bin = "true"  # a no-op that exits 0


def _joined(*, stash: bool, install: bool) -> str:
    return " && ".join(_build_sync_commands(_Host(), ".", stash, install))


def _exit_status_of(chain: str) -> int:
    """Run a chain in a real shell, with `false` standing in for a failing step."""
    return subprocess.run(
        ["bash", "-c", chain], capture_output=True, text=True
    ).returncode


def test_failing_step_still_fails_the_chain_when_stash_is_enabled():
    # ARRANGE: the stash path is the one that appends the tolerant command.
    chain = _joined(stash=True, install=False).replace("git pull", "false")
    # ACT
    status = _exit_status_of(chain)
    # ASSERT: the pre-fix chain returned 0 here — that WAS the bug.
    assert status != 0


def test_failing_step_still_fails_the_chain_when_install_is_enabled():
    # ARRANGE: install appends a second `|| true` (the .venv symlink).
    chain = _joined(stash=False, install=True).replace("git pull", "false")
    # ACT
    status = _exit_status_of(chain)
    # ASSERT
    assert status != 0


def test_failing_step_still_fails_the_chain_with_both_tolerant_commands():
    # ARRANGE: both `|| true` sites present at once.
    chain = _joined(stash=True, install=True).replace("git pull", "false")
    # ACT
    status = _exit_status_of(chain)
    # ASSERT
    assert status != 0


def test_clean_chain_succeeds_so_the_guard_is_not_vacuous():
    # ARRANGE: a POSITIVE CONTROL. Without it, a chain that always failed
    # would satisfy every assertion above while breaking sync entirely.
    chain = _joined(stash=True, install=True).replace("git ", "true ")
    # ACT
    status = _exit_status_of(chain)
    # ASSERT
    assert status == 0
