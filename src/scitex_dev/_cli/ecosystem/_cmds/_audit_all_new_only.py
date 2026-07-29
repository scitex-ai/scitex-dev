#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The diff-aware `--new-only` execution path for `ecosystem audit-all`.

Stages the base ref in a detached worktree, runs the SAME `audit-all`
against it, diffs the violation key sets against the HEAD run, and re-emits
only net-new findings. Falls back to a strict audit on setup failure.

Split out of `_audit_all.py` (544 lines, cap 512) — it spawns a child
audit, stages a git worktree and owns its own exit semantics, so it is a
separate responsibility rather than a branch of the command body. See
GITIGNORED/REFACTORING.md.

WHY THIS PATH IS SAFETY-CRITICAL
--------------------------------
Measured 2026-07-29 on scitex-dev PR #457 (run 30447489901): the REQUIRED
`audit` check printed

    ERRO:   [§2] ... mutating verb 'install' missing --yes/-y flag
    ERRO:   [E] [PS-202 ...] .../_rules: no matching tests/.../_rules/
    --new-only: 0 net-new violation(s)

and exited 0. Both violations were genuinely new — neither file existed on
the base ref. The same commit's `tests` legs failed on the audit gate test,
proving the findings were real. The exit status followed the FILTER'S TALLY
rather than the findings, so a required merge gate printed errors and
passed.

`net_new = head_keys - base_keys`, so an empty result means the baseline
reproduced every HEAD finding. Two ways that happens: the PR genuinely adds
nothing, or the baseline graded the wrong tree / did not run. Those were
previously indistinguishable, because the baseline's own output is captured,
diffed and discarded — nobody could see what it graded.

This module keeps the filter (it exists for a real reason: inherited debt
must not block unrelated PRs) but makes it accountable:

  * a baseline that did not run is UNKNOWN, not zero — refuse to subtract it
  * always print the resolved baseline commit and the suppressed count
  * flag the base-equals-head signature explicitly

Per constitution §2, a blanket flag is still the wrong long-term mechanism
for grandfathering; per-rule config exemptions with written reasons are.
This makes the flag honest in the meantime.
"""

from __future__ import annotations

import subprocess
import sys as _sys
from pathlib import Path

import click


def resolve_ref(repo: Path, ref: str) -> str:
    """Return the commit `ref` resolves to in `repo`, or a marker string.

    Printed in the verdict so a reader can tell WHICH baseline was used.
    Never raises: a diagnostic must not be able to break the run it
    describes.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", ref],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "<unresolvable>"
    if proc.returncode != 0:
        return "<unresolvable>"
    return proc.stdout.strip() or "<unresolvable>"


def run_new_only_and_exit(
    *,
    head_path: Path,
    distribution: str,
    since_ref: str,
    head_combined: str,
    head_exit: int,
    scitex_dev_bin: str,
    sub_env: dict,
) -> None:
    """Run the `--new-only` comparison and exit the process with its verdict.

    Never returns — every path ends in `SystemExit`.
    """
    from ...audit._diff import (
        DiffAwareSetupError,
        compute_net_new,
        extract_violation_keys,
        filter_to_net_new_lines,
        worktree_at,
    )

    try:
        with worktree_at(head_path, since_ref) as base_path:
            # Spawn audit-all in a child process pointed at the base
            # worktree, using the SAME scitex-dev binary the dispatcher
            # resolved so the rule corpus matches across the diff.
            base_proc = subprocess.run(
                [
                    scitex_dev_bin,
                    "ecosystem",
                    "audit-all",
                    distribution,
                    "--path",
                    str(base_path),
                    "--no-version-check",
                ],
                capture_output=True,
                text=True,
                env=sub_env,
            )
            base_combined = base_proc.stdout + "\n" + base_proc.stderr
            base_returncode = base_proc.returncode
    except DiffAwareSetupError as e:
        click.echo(
            f"warning: --new-only setup failed ({e}); falling back to strict audit.",
            err=True,
        )
        click.echo(head_combined)
        _sys.exit(head_exit)

    # A baseline audit that DID NOT RUN is not a baseline of zero findings —
    # it is UNKNOWN, and subtracting an unknown set silently suppresses
    # everything. `audit-all` exits 0 (clean) or 1 (findings); any other
    # status means the baseline run itself failed.
    if base_returncode not in (0, 1):
        click.echo(
            f"error: --new-only baseline audit at {since_ref} exited "
            f"{base_returncode} (expected 0=clean or 1=findings), so its "
            "violation set is UNKNOWN. Refusing to subtract an unknown "
            "baseline — reporting the FULL HEAD audit instead.",
            err=True,
        )
        click.echo(head_combined)
        _sys.exit(head_exit)

    base_resolved = resolve_ref(head_path, since_ref)
    head_keys = extract_violation_keys(head_combined, distribution_filter=distribution)
    base_keys = extract_violation_keys(base_combined, distribution_filter=distribution)
    net_new = compute_net_new(head_combined, base_combined, distribution=distribution)

    click.echo(filter_to_net_new_lines(head_combined, net_new, distribution=distribution))
    click.echo("", err=True)

    # DISCLOSE THE DENOMINATOR. The old line reported only the net-new
    # count, so a run that suppressed every finding was indistinguishable
    # from a run that found nothing.
    click.echo(
        f"--new-only: {len(net_new)} net-new violation(s) "
        f"({distribution} HEAD vs {since_ref} = {base_resolved}); "
        f"{len(head_keys)} finding(s) at HEAD, {len(base_keys)} at baseline, "
        f"{len(head_keys) - len(net_new)} suppressed as pre-existing",
        err=True,
    )

    # A baseline reproducing EVERY HEAD finding is the signature of a
    # baseline that graded the wrong tree (e.g. a sub-auditor resolving via
    # cwd instead of the staged worktree). Not proof — a PR that genuinely
    # adds nothing looks identical — so disclose rather than fail.
    if head_keys and base_keys == head_keys:
        click.echo(
            "note: the baseline reported exactly the same finding set as HEAD, "
            "so --new-only suppressed all of them. If this change does add "
            "findings, the baseline graded the wrong tree — re-run without "
            "--new-only to see the full result.",
            err=True,
        )

    _sys.exit(1 if net_new else 0)


__all__ = ["resolve_ref", "run_new_only_and_exit"]

# EOF
