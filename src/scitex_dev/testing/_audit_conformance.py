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
import shlex
import shutil
import subprocess
from pathlib import Path


SKIP_ENV_VAR = "SCITEX_DEV_SKIP_AUDIT"


def audit_all_for_package(
    distribution: str,
    *,
    path: str | Path | None = None,
    timeout: float = 550.0,
    skip_rules: tuple[str, ...] = (),
) -> None:
    """Run `scitex-dev ecosystem audit-all <distribution>` and assert exit 0.

    Parameters
    ----------
    distribution
        ECOSYSTEM key (e.g. ``"scitex-io"``, ``"scitex-stats"``,
        ``"socialia"``).
    path
        The checkout to audit — pass it, and pass the tree the test
        itself lives in. PASS THIS. Without it, `audit-all` has no
        argument telling it WHICH tree you meant, so it falls back to
        resolving the distribution by import location / a
        ``~/proj/<name>`` development guess. On a CI runner that guess
        is somebody else's tree — or the wrong commit of your own — and
        the gate then grades source that is NOT the commit under test
        while reporting a confident pass/fail. A gate that grades the
        wrong tree is worse than no gate.

        The idiomatic call from a package's ``tests/test_audit.py`` is
        therefore to anchor on the test file itself, which is by
        construction inside the checkout pytest is running against::

            from pathlib import Path
            audit_all_for_package(
                "scitex-io", path=Path(__file__).resolve().parents[1]
            )

        Threaded through as ``--path <path>`` to the ``audit-all`` CLI,
        which forwards it to every sub-auditor that accepts it
        (`audit-project`, `audit-django`, `audit-python-apis` — the
        source-tree-reading ones). The distribution NAME is still
        required and is still used for skill/rule lookup; ``path`` only
        decides which source gets read.

        ``None`` (the default) preserves the historical
        resolve-by-guess behaviour for callers that haven't migrated.
        It is a compatibility shim, not a recommendation.
    timeout
        Per-test wall-clock cap. `audit-all` fans out to SIX
        sub-auditors (`audit-cli`, `audit-mcp-tools`, `audit-skills`,
        `audit-python-apis`, `audit-project`, `audit-django`), each a
        fresh Python subprocess that re-imports the target package —
        real measured wall-clock on a loaded/NFS-backed host runs well
        past the previous 120s default even when the audit itself is
        completely clean (verified directly: `scitex-dev ecosystem
        audit-all scitex-dev --path <worktree>` exits 0, and a bare
        untimed run completed clean end-to-end in ~455s under load).
        120s was tuned for "a slow PyPI install," not for the
        six-subprocess audit sweep itself. 550s gives real headroom
        while staying under the ``test_audit_all_clean`` call site's
        ``@pytest.mark.timeout(600)`` override (see
        ``tests/develop/test_audit.py`` / the
        ``ecosystem install-audit-gate`` template that generates it
        for every other package) so THIS subprocess timeout fires
        first with a readable audit-output error message, instead of
        pytest-timeout's generic SIGALRM traceback winning the race. A
        genuinely wedged auditor still times out, just later.

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
    argv = [bin_path, "ecosystem", "audit-all", distribution]
    if path is not None:
        argv += ["--path", str(path)]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1"},
    )
    if proc.returncode != 0 and skip_rules:
        # Re-classify: if every contributing violation in stdout is on
        # the caller's allow-list, treat as clean. Auditors print rule
        # lines in two shapes:
        #   `  [E] [PSnnn §M] …`       (legacy, from audit-summary)
        #   `  [PSnnn §M] <where>: …`  (canonical, used by every current auditor)
        # Match by rule id alone — the surrounding marker is incidental.
        skipped: list[str] = []
        non_skipped: list[str] = []
        for line in (proc.stdout + "\n" + proc.stderr).splitlines():
            stripped = line.lstrip()
            # Accept any line whose first bracketed token contains a rule id.
            # Current auditors prefix with a coloured level word (`ERRO: `,
            # `WARN: `) — strip a trailing-colon word before the bracket
            # check so the rule id is reachable.
            head = stripped.split(":", 1)
            payload = (
                head[1].lstrip() if len(head) == 2 and head[0].isalpha() else stripped
            )
            if not (payload.startswith("[") or payload.startswith("[E]")):
                continue
            matched = [r for r in skip_rules if f"[{r} " in line or f"[{r}]" in line]
            if matched:
                skipped.append(stripped)
            else:
                non_skipped.append(line)
        # Only mask the failure when skip_rules ACTUALLY matched something.
        # Without that guard, any non-zero exit (e.g. a warn-level sub-auditor
        # with no [E] lines) gets silently swallowed simply because the caller
        # passed *some* skip_rules — the previous behaviour and a real
        # visibility bug.
        if skipped and not non_skipped:
            # Surface a UserWarning so reviewers see exactly what's masked.
            # Tests still pass; the warning is what catches regression of an
            # in-progress cleanup that should now be removable from skip_rules.
            import warnings

            head = skipped[0][:120].rstrip()
            more = f" (+{len(skipped) - 1} more)" if len(skipped) > 1 else ""
            warnings.warn(
                f"audit-all: {len(skipped)} violation(s) masked by "
                f"skip_rules={list(skip_rules)} on {distribution}: "
                f"{head}{more}",
                UserWarning,
                stacklevel=2,
            )
            return
    if proc.returncode != 0:
        # Reproduce the ACTUAL argv (including any --path) so the printed
        # command re-runs the same audit against the same tree. A hand-
        # written command string would silently drop --path and send the
        # reader off to reproduce against a different checkout.
        cmd = shlex.join(argv)
        msg = (
            f"audit-all reported violations for {distribution!r} "
            f"(exit={proc.returncode}).\n"
            f"  $ {cmd}\n\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
        raise AssertionError(msg)


__all__ = ["audit_all_for_package"]
