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

import re
import subprocess
import sys as _sys
from collections.abc import Sequence
from pathlib import Path

import click

# Any line the auditors emit in `LEVEL:   [TAG] ...` shape is a FINDING,
# whether or not the violation-key parser happens to understand it.
_FINDING_SHAPED = re.compile(r"^(?P<level>ERRO|WARN|INFO):\s+\[")


def drop_masked_lines(combined: str, report) -> str:
    """Remove lines a declared ``audit.skip-rules`` entry already masked.

    WHY THIS EXISTS. `--new-only` used to diff RAW sub-auditor output, so
    `skip-rules` masked correctly in a strict local run and masked NOTHING on
    the path CI actually takes. A maintainer configured it, verified the mask
    locally, shipped, and the rule kept firing in CI while the config file
    said it was handled — a suppression that cannot suppress, failing in the
    direction that wastes the most time. Reported by scitex-cards 2026-08-10.

    MASKING THE HEAD SIDE ALONE IS SUFFICIENT AND SAFE, which is the
    non-obvious part. The base side runs its own audit in a worktree and its
    output is unmasked, so the diff is deliberately asymmetric::

        masked in BOTH      absent from HEAD, present in BASE  -> not net-new
        masked, NEW in HEAD absent from HEAD                   -> not net-new
        unmasked, NEW       unaffected                         -> net-new

    No false net-new can be introduced by removing lines from HEAD only: a
    line that is gone from HEAD can never be counted as newly appearing there.

    The alternative — making `skip-rules` REFUSE loudly under `--new-only` —
    was rejected: it breaks every repo with a working config today in order to
    fix a defect whose only effect was being too permissive.

    ``report`` is a ``MaskReport``; ``report.masked`` maps rule -> matched
    lines. Passing one with nothing masked (or ``None``) returns ``combined``
    unchanged, so the zero-skip-rules case costs nothing.
    """
    masked = {
        line for hits in (getattr(report, "masked", None) or {}).values() for line in hits
    }
    if not masked:
        return combined
    return "\n".join(
        line for line in combined.splitlines() if line.strip() not in masked
    )


def unparsed_finding_lines(text: str, roots: tuple[str, ...]) -> set[str]:
    """Finding-shaped lines that produce NO violation key, path-normalised.

    Measured 2026-07-29 on real audit output: **9 finding lines in, 1 key
    out**. `_FINDING_RE` only matches ``LEVEL: [TAG] <single-token-dist>:
    <msg>``, so both real ERROR shapes are dropped —
    ``[§2] scitex-dev ecosystem <cmd>: ...`` (subject is a subcommand path,
    not a bare dist token) and ``[E] [PS-202 ...] /path: ...`` (two bracket
    groups). Those findings were invisible to the diff AND reprinted as
    prose by the line filter, which is how the required gate printed errors
    and exited 0.

    Rather than pretend the parser covers everything, diff the raw TEXT of
    what it could not parse. `roots` are checkout paths stripped before
    comparison: the baseline runs in a temporary worktree, so every
    absolute path differs and an unnormalised compare would call every
    line new.
    """
    from ...audit._diff import _FINDING_RE

    out: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not _FINDING_SHAPED.match(line):
            continue
        if _FINDING_RE.match(line):
            continue  # the key-based diff already covers it
        for root in roots:
            if root:
                line = line.replace(root, "<TREE>")
        out.add(line)
    return out


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
    scitex_dev_argv: Sequence[str],
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
            # worktree, using the SAME scitex-dev the dispatcher
            # resolved so the rule corpus matches across the diff.
            #
            # An ARGV, not a binary path: the dispatcher resolves
            # `[sys.executable, "-m", "scitex_dev"]` so the audit works
            # where the console script is not on PATH. Splatting it keeps
            # the two sides of the diff running the same interpreter.
            base_proc = subprocess.run(
                [
                    *scitex_dev_argv,
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
            # Kept for path normalisation after the worktree is torn down:
            # the baseline's absolute paths differ from HEAD's, so a raw
            # text diff must strip both roots or every line looks new.
            base_path_used = str(base_path)
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
    # The two trees live at different paths by construction, so BOTH halves of
    # this diff must strip them. The raw-text half below always did; the KEY
    # half did not, and that asymmetry made every directory-bearing finding
    # look net-new. Computed here, above its first use, rather than at the
    # text diff — one definition, both consumers.
    roots = (str(base_path_used), str(head_path))
    head_keys = extract_violation_keys(
        head_combined, distribution_filter=distribution, roots=roots
    )
    base_keys = extract_violation_keys(
        base_combined, distribution_filter=distribution, roots=roots
    )
    net_new = compute_net_new(
        head_combined, base_combined, distribution=distribution, roots=roots
    )

    # FALLBACK DIFF for findings the key parser cannot read. Without this
    # they are invisible in BOTH directions: absent from the key diff, and
    # reprinted verbatim by `filter_to_net_new_lines` (which preserves any
    # line it does not recognise as a finding) — so the run showed errors
    # and counted none. Compare their raw text instead of pretending they
    # do not exist.
    head_unparsed = unparsed_finding_lines(head_combined, roots)
    base_unparsed = unparsed_finding_lines(base_combined, roots)
    net_new_unparsed = head_unparsed - base_unparsed
    net_new_unparsed_errors = {ln for ln in net_new_unparsed if ln.startswith("ERRO")}

    click.echo(
        filter_to_net_new_lines(
            head_combined, net_new, distribution=distribution, roots=roots
        )
    )
    click.echo("", err=True)

    # DISCLOSE THE DENOMINATOR. The old line reported only the net-new
    # count, so a run that suppressed every finding was indistinguishable
    # from a run that found nothing.
    total_net_new = len(net_new) + len(net_new_unparsed)
    click.echo(
        f"--new-only: {total_net_new} net-new finding(s) "
        f"({distribution} HEAD vs {since_ref} = {base_resolved}); "
        f"keyed: {len(net_new)} new of {len(head_keys)} at HEAD "
        f"({len(base_keys)} at baseline); "
        f"unkeyed: {len(net_new_unparsed)} new of {len(head_unparsed)} at HEAD "
        f"({len(base_unparsed)} at baseline)",
        err=True,
    )
    if head_unparsed:
        # Disclose the parser's own coverage. An auditor that cannot say how
        # much of its input it understood is reporting a number without a
        # denominator.
        click.echo(
            f"note: {len(head_unparsed)} finding line(s) are not readable by the "
            "violation-key parser and were compared as raw text instead. "
            "Measured 2026-07-29: 9 finding lines in, 1 key out — the parser "
            "only matches `LEVEL: [TAG] <dist>: <msg>`.",
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

    if net_new_unparsed_errors:
        # These are ERROR-severity findings that are genuinely new and that
        # the key diff could not see. Print them explicitly — they would
        # otherwise sit in the output indistinguishable from narration.
        click.echo(
            f"error: {len(net_new_unparsed_errors)} net-new ERROR finding(s) "
            "not readable by the violation-key parser:",
            err=True,
        )
        for line in sorted(net_new_unparsed_errors):
            click.echo(f"  {line}", err=True)

    # A finding the filter cannot classify must FAIL OPEN. Reclassifying it
    # as prose is what let a required gate print errors and exit 0.
    _sys.exit(1 if (net_new or net_new_unparsed) else 0)


__all__ = ["resolve_ref", "run_new_only_and_exit"]

# EOF
