# -*- coding: utf-8 -*-
"""Per-check new-vs-baseline severity escalation.

Written for PS-214/PS-215 (empty pyproject extras / dead install-remedy
strings — see `_check_empty_extras.py` / `_check_install_remedy_strings.py`)
in response to a scitex-writer report: both rules shipped flat `severity =
"W"` (warn-only), so a violation with no escalation path is "a finding
printed under a green banner" — the exact defect class the rules exist to
catch. scitex-writer's own `editor = []` sat undetected through repeated
audit runs specifically because nothing distinguished it from routine
warning noise.

This module intentionally does NOT reinvent git-diffing. The repo already
has a diff-aware baseline mechanism — `scitex_dev._cli.audit._diff` — built
for `ecosystem audit-all --new-only --since BASE_REF` (lead task #40 part
b; CI wiring in `.github/workflows/*quality-audit*.yml` and the
`pr-ci.yml.tmpl` template, both requiring `fetch-depth: 0`). That mechanism
diffs two FULL audit-run stdout streams and *drops* lines already present
at baseline — coarse, and only invoked when the caller opts in with
`--new-only`.

PS-214/PS-215 need a different shape: severity itself must depend on
new-vs-existing, on every run (not just an opt-in flag), and a
pre-existing violation must still be REPORTED (just non-blocking) rather
than silently dropped — that's the whole point of the fix (an
already-red repo shouldn't have its backlog erased from view, only
un-blocked). So this module reuses the diff mechanism's core primitive —
`worktree_at`, the git-worktree-based baseline staging — but applies it
at the single-check level: re-run the SAME check function against a
`worktree_at`-staged baseline ref, then escalate (not drop) any current
violation absent from that baseline run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from .._diff import DiffAwareSetupError, worktree_at
from ._violation import Violation

# Mirrors `ecosystem audit-all --since`'s default (`_audit_all.py`). A
# plain local `develop` branch resolves in an ordinary dev checkout; CI
# checkouts (`fetch-depth: 0`) typically only carry the remote-tracking
# `origin/develop`, so that is tried as a fallback below.
DEFAULT_BASELINE_REF = "develop"


def _violation_identity(v: Violation, repo: Path) -> tuple[str, str, str]:
    """Repo-relative, line-stable identity for one violation.

    Mirrors the trade-off documented in `_diff.ViolationKey`: line numbers
    are dropped so an unrelated edit that shifts a `where:LINE` suffix
    does not re-key an untouched pre-existing violation as "new". Absolute
    `where` paths are relativized against `repo` so the SAME logical
    finding compares equal between the real repo and a `worktree_at`
    tempdir checkout (different absolute prefixes, same relative shape).
    """
    where = v.where
    try:
        p = Path(where)
        if p.is_absolute():
            where = str(p.relative_to(repo))
    except (ValueError, OSError):
        pass
    head, sep, tail = where.rpartition(":")
    if sep and tail.isdigit():
        where = head
    return (v.rule, where, v.detail)


def escalate_new_violations(
    repo: Path,
    current: list[Violation],
    rule_codes: Sequence[str],
    recheck: Callable[[Path], list[Violation]],
    *,
    baseline_ref: str = DEFAULT_BASELINE_REF,
) -> None:
    """Escalate violations that are NEW relative to ``baseline_ref``.

    For every violation in ``current`` whose ``rule`` is in
    ``rule_codes``: if an equivalent violation (same repo-relative
    identity) is NOT present when ``recheck`` is re-run against a
    `worktree_at`-staged checkout of ``baseline_ref``, it is genuinely
    new — introduced by the change under audit — and gets
    ``severity_override = "E"`` (blocking). A violation already present
    at baseline is pre-existing backlog; it is left with
    ``severity_override = None``, so it falls back to the rule's
    registered default (currently "W" — warn, non-blocking) rather than
    newly blocking an already-red repo.

    Degrades silently (no escalation — every targeted violation keeps
    the rule's default severity) when no baseline ref can be resolved:
    a repo with no `.git` (unit-test fixtures, a tarball checkout), or a
    shallow clone where neither ``baseline_ref`` nor
    ``origin/<baseline_ref>`` exists locally (missing `fetch-depth: 0`).
    An unresolvable baseline must never newly BLOCK a check that had no
    way to tell new from old — mirrors `worktree_at`'s own documented
    "degrade gracefully" contract.
    """
    targeted = [v for v in current if v.rule in rule_codes]
    if not targeted:
        return

    candidates = [baseline_ref]
    if not baseline_ref.startswith("origin/"):
        candidates.append(f"origin/{baseline_ref}")

    baseline_ids: set[tuple[str, str, str]] | None = None
    for ref in candidates:
        try:
            with worktree_at(repo, ref) as base_path:
                baseline_ids = {
                    _violation_identity(v, base_path) for v in recheck(base_path)
                }
            break
        except DiffAwareSetupError:
            continue

    if baseline_ids is None:
        return

    for v in targeted:
        v.severity_override = "E" if _violation_identity(v, repo) not in baseline_ids else None


__all__ = ["DEFAULT_BASELINE_REF", "escalate_new_violations"]


# EOF
