"""`audit_all_for_package` — pytest assertion that `audit-all <pkg>` is clean.

Each ecosystem package drops a one-liner `tests/test_audit.py` that
calls this helper. A non-zero exit (any error-severity violation,
not-auditable status, or sub-process launch failure) raises
AssertionError so pytest reports it as a normal test failure.

Subprocess invocation, not in-process, because:

  - The umbrella `scitex-dev ecosystem audit-all` is what users actually
    run; the test mirrors it byte-for-byte.
  - Each sub-auditor isolates stdio (some packages close fd 1 on import).
    Re-entering them in-process from pytest would interact badly with
    pytest's own capture machinery.
"""

from __future__ import annotations

import os
import shutil
import subprocess


SKIP_ENV_VAR = "SCITEX_DEV_SKIP_AUDIT"


def audit_all_for_package(distribution: str, *, timeout: float = 120.0) -> None:
    """Run `scitex-dev ecosystem audit-all <distribution>` and assert exit 0.

    Parameters
    ----------
    distribution
        ECOSYSTEM key (e.g. ``"scitex-io"``, ``"scitex-stats"``,
        ``"socialia"``).
    timeout
        Per-test wall-clock cap; covers a slow PyPI install in CI.

    Bypass
    ------
    Set ``SCITEX_DEV_SKIP_AUDIT=1`` in the environment to skip the
    audit (the test calls ``pytest.skip`` instead of running the
    subprocess). Use during a remediation push when pre-existing
    violations would block unrelated test runs, or when developing
    locally without scitex-dev's audit corpus available. CI for
    release branches MUST NOT set this — drift goes silent.

    Raises
    ------
    AssertionError
        If the subprocess returns non-zero. The full stdout + stderr
        are included in the message so the failing rule is visible in
        the test report without re-running the audit by hand.
    """
    if os.environ.get(SKIP_ENV_VAR):
        import pytest

        pytest.skip(
            f"audit-all skipped via {SKIP_ENV_VAR}=1 (unset to re-enable the gate)"
        )
    bin_path = shutil.which("scitex-dev") or "scitex-dev"
    proc = subprocess.run(
        [bin_path, "ecosystem", "audit-all", distribution],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1"},
    )
    if proc.returncode != 0:
        # Build a single message that pytest will print verbatim. Keep
        # the command line at the top so a copy-paste re-runs the audit
        # exactly.
        cmd = f"{bin_path} ecosystem audit-all {distribution}"
        msg = (
            f"audit-all reported violations for {distribution!r} "
            f"(exit={proc.returncode}).\n"
            f"  $ {cmd}\n\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
        raise AssertionError(msg)


__all__ = ["audit_all_for_package"]
