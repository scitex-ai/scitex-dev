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
import sys
from pathlib import Path


SKIP_ENV_VAR = "SCITEX_DEV_SKIP_AUDIT"


def guessed_path_warning(cwd: Path | None = None) -> str:
    """The message emitted when ``path`` is omitted, NAMING the guess.

    ``path=None`` is documented as a compatibility shim, not a
    recommendation — but it is also the default every caller gets, so
    the documented-wrong shape used to be the SILENT one. Guessing is
    tolerable; guessing without saying from where is what makes a
    wrong-tree audit cost minutes: the run's output looks internally
    consistent, and nobody double-checks a subject that was never
    stated.
    """
    here = Path.cwd() if cwd is None else Path(cwd)
    return (
        "warning: audit_all_for_package(path=None) — no tree was pinned, "
        f"so `audit-all` will resolve the target itself, guessing from "
        f"cwd {here}. If that is not the checkout under test (a git "
        "worktree, or a shared CI runner with a sibling checkout), the "
        "gate grades the WRONG tree and still reports a confident "
        "pass/fail. Pass path=Path(__file__).resolve().parents[N] with N "
        "counting the directory levels from the test file up to the "
        "package root."
    )


def warn_on_guessed_path(cwd: Path | None = None, stream=None) -> str:
    """Emit :func:`guessed_path_warning` to ``stream`` and return it.

    stderr by default. Deliberately NOT `warnings.warn`: packages that
    run pytest with `-W error` would turn a diagnostic into a hard
    failure of a gate that is otherwise working, and this warning must
    reach every existing caller, not only the ones whose filter config
    tolerates it.
    """
    text = guessed_path_warning(cwd)
    print(text, file=sys.stderr if stream is None else stream)
    return text


#: Rule ids that describe THE MEASUREMENT or the REPORT rather than the code,
#: so they can never be a violation of it. Mirrors
#: :data:`scitex_dev._cli.audit._diff.NON_ATTRIBUTABLE_RULES`, which already
#: knew this and which this module did not consult.
#:
#: `§10w` is the import-budget auditor saying COULD NOT MEASURE RELIABLY — a
#: deliberate warn-tier "no verdict". Counting it as a violation collapses
#: UNKNOWN into the failure pole, which is the exact three-valued-signal
#: error the constitution names. Measured 2026-08-09 on scitex-hub: one such
#: notice discarded a 151-line skip mask and reddened a green tree.
#:
#: `defer` is the `[defer] ... N finding(s) suppressed` NOTICE — arithmetic
#: about the report, not a finding in it. Reported 2026-07-21 and worked
#: around downstream by adding "defer" to a package's skip_rules, which is
#: precisely why the defect survived to reappear as `§10w` nineteen days
#: later. Both belong here.
_NON_VIOLATION_RULES: "frozenset[str]" = frozenset(
    {"§10", "§10w", "TALLY", "defer"}
)

#: Level words that are NOT failures. The auditors already print severity;
#: this module used to strip it only to reach the bracket and then ignore it.
_NON_VIOLATION_LEVELS: "frozenset[str]" = frozenset({"WARN", "INFO", "SUCC", "NOTE"})

#: Level words that ARE failures. Needed separately from the non-violation
#: set because an UNBRACKETED line has no rule id to fall back on, so "not a
#: known warn word" is too weak a test — a line prefixed with any random
#: `word:` would qualify. Here the level must be positively recognised.
_ERROR_LEVELS: "frozenset[str]" = frozenset(
    {"ERRO", "ERROR", "FAIL", "FAILED", "FATAL", "CRIT", "CRITICAL"}
)


def _is_error_tier(level: str) -> bool:
    """Is this level word an error, positively identified?

    Used only for lines with NO rule bracket, where there is no rule id to
    reason about and the level word is the entire signal.

    Deliberately a whitelist. The inverse test — "not in
    ``_NON_VIOLATION_LEVELS``" — would promote any unrecognised `word:`
    prefix to an error, so a line like ``note: skipping`` or a stray
    ``usage:`` would fail the gate. Given this branch exists to make a
    silent pass become a red build, being wrong in that direction produces
    unexplainable failures, which is how a gate gets disabled wholesale.
    """
    return level.strip().upper() in _ERROR_LEVELS


def _is_gate_violation(level: str, payload: str) -> bool:
    """Does this reported line actually fail the gate?

    Three kinds of bracketed line reach the classifier and only one is a
    violation:

    * ``ERRO: [PS-204 §2 ...]``  — a finding. Counts.
    * ``WARN: [§10w ...]``       — a NOTICE about the measurement. Does not.
    * ``[defer] ... N finding(s) suppressed`` — arithmetic. Does not.

    The previous implementation counted all three, so a single warn-tier
    notice discarded an entire skip-rule mask (the guard is
    ``if skipped and not non_skipped``) and turned a green tree red.

    That defect was reported on 2026-07-21 for the ``[defer]`` notice and
    worked around downstream by adding "defer" to a package's skip_rules —
    which is why it survived to reappear as ``§10w`` nineteen days later.
    Masking a could-not-measure notice suppresses the one signal saying the
    measurement is untrustworthy, so the fix belongs here, not in any
    consumer's skip list.
    """
    if level in _NON_VIOLATION_LEVELS:
        return False
    return not any(
        payload.startswith(f"[{rule} ") or payload.startswith(f"[{rule}]")
        for rule in _NON_VIOLATION_RULES
    )


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

        The idiomatic call from a package's audit gate is therefore to
        anchor on the test file itself, which is by construction inside
        the checkout pytest is running against. **N counts the DIRECTORY
        levels from the test file up to the package root, so it depends
        on where the gate lives** — copying an N from an example written
        for a different depth silently anchors on a SUBDIRECTORY, and
        the audit then grades that subdirectory as if it were the
        package::

            # tests/test_audit.py           -> parents[1]
            # tests/develop/test_audit.py   -> parents[2]   <- the shape
            #                                  `ecosystem install-audit-gate`
            #                                  generates
            from pathlib import Path
            audit_all_for_package(
                "scitex-io", path=Path(__file__).resolve().parents[2]
            )

        (`ecosystem install-audit-gate` derives N from the path it is
        about to write rather than hardcoding it — see
        ``_cli.ecosystem._cmds._install_gate.anchor_depth``.)

        Threaded through as ``--path <path>`` to the ``audit-all`` CLI,
        which forwards it to ALL SIX sub-auditors. Every one of them
        reads the source tree, so every one of them needs it:
        `audit-project`, `audit-django`, `audit-python-apis`,
        `audit-skills`, `audit-mcp-tools`, and `audit-cli` — the last
        one reads the tree twice over, for its static §2/§11 source
        scans AND for the per-package
        ``.scitex/dev/cli-audit-dict.yaml`` custom dictionary. (An
        earlier version of this docstring listed only the first three,
        which is how audit-cli's dictionary lookup stayed cwd-rooted
        long enough to bite scitex-storage: four auditors printed
        ``via explicit`` while audit-cli graded another checkout's dict,
        and the run's output looked internally consistent.) The
        distribution NAME is still required and is still used for
        skill/rule lookup; ``path`` only decides which source gets read.

        ``None`` (the default) preserves the historical
        resolve-by-guess behaviour for callers that haven't migrated.
        It is a compatibility shim, not a recommendation — and it is no
        longer SILENT: omitting ``path`` prints a warning to stderr
        naming the cwd the guess will start from (see
        :func:`warn_on_guessed_path`).
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
    if path is None:
        # Before the skip check: a caller who bypasses the audit still
        # benefits from learning their gate is shaped wrong, and a
        # warning that only fires on the non-skipped path is a warning
        # that goes missing exactly when the run is least scrutinised.
        warn_on_guessed_path()
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
            has_level = len(head) == 2 and head[0].isalpha()
            level = head[0].strip().upper() if has_level else ""
            payload = head[1].lstrip() if has_level else stripped
            if not (payload.startswith("[") or payload.startswith("[E]")):
                # AN ERROR WITHOUT A RULE ID STILL COUNTS, and it is the one
                # kind of finding that can never be masked.
                #
                # This line used to be a bare `continue`, which dropped such
                # lines into NEITHER bucket. They then could not appear in
                # `non_skipped`, so the `if skipped and not non_skipped` guard
                # below masked the whole failure — a gate passing on the
                # strength of an error it did not know how to read.
                #
                # The lines that hit this path are the ones that matter most:
                # the auditor reporting it could not RUN. Measured in the wild
                # — scitex-hub's CI has carried
                #     Error: No module named 'requests'
                # since 2026-08-05, visible in the log and invisible to this
                # classifier for four days.
                #
                # Masking is keyed on rule id, so a line carrying no rule id
                # cannot be matched by any skip_rules entry. That is correct
                # by design: an auditor that could not run must not be
                # maskable. It also means this branch can only ever ADD to
                # `non_skipped`, never to `skipped`.
                if _is_error_tier(level):
                    non_skipped.append(line)
                continue
            if not _is_gate_violation(level, payload):
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


__all__ = [
    "audit_all_for_package",
    "guessed_path_warning",
    "warn_on_guessed_path",
]
