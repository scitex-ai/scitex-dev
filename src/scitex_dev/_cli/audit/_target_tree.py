"""Deterministic audit target-tree resolution: explicit > cwd > registry.

Operator directive (2026-07-21): audits must land on the tree the CALLER
meant. Auditing the develop checkout is legitimate in itself; the defect
is a resolution that silently goes somewhere the caller didn't intend.

Reference incident (same day): on a CI runner,
``audit_all_for_package('scitex-dev')`` with no explicit path resolved
the operator's ``~/proj/scitex-dev`` develop checkout via the ecosystem
registry's ``local_path`` instead of the CI checkout the calling test
lived in — the gate graded a different tree than the commit under test.
The registry lookup used to OUTRANK the caller's own working tree; this
module inverts that.

Precedence (first hit wins), shared by every per-target audit CLI
(``audit-project`` / ``audit-django`` / ``audit-python-apis``, and
therefore by ``ecosystem audit-all`` which shells out to them):

  a. ``explicit`` — an explicit ``--path`` / ``--repo``. Always wins.
  b. ``cwd``      — the git toplevel of the current working directory
                    (``git rev-parse --show-toplevel``; works inside
                    linked worktrees), iff that tree IS a checkout of
                    the requested distribution — its pyproject
                    ``[project].name`` matches the requested name under
                    PEP-503 normalization (case / ``-`` / ``_`` / ``.``
                    folded). Makes worktree and CI invocations
                    self-targeting.
  c. ``registry`` — the ecosystem registry's ``local_path``. The
                    historical behaviour, still right for cross-package
                    audits (``ecosystem audit-all all`` run from
                    anywhere).

Unresolved → ``(None, None)``: the downstream auditor then applies its
legacy import-location / ``~/proj/<name>`` guess (surfaced as ``import``
/ ``proj-guess`` by ``_project._discovery``).

The chosen rule is threaded into the #392 resolved-tree banner
(``via <rule>``) so a wrong-tree surprise is diagnosable at a glance.
"""

from __future__ import annotations

import re
from pathlib import Path

_PEP503_RE = re.compile(r"[-_.]+")


def normalize_dist_name(name: str) -> str:
    """PEP-503-normalize a distribution name.

    Lowercases and collapses every run of ``-`` / ``_`` / ``.`` to a
    single ``-`` — ``Demo_Pkg.x`` and ``demo-pkg-x`` are the same
    distribution as far as any index (and this resolver) is concerned.
    """
    return _PEP503_RE.sub("-", name.strip()).lower()


def dist_names_match(a: str, b: str) -> bool:
    """True iff ``a`` and ``b`` name the same distribution (PEP-503)."""
    return normalize_dist_name(a) == normalize_dist_name(b)


def cwd_checkout_of(distribution: str, cwd: Path | None = None) -> Path | None:
    """Return the git toplevel of ``cwd`` iff it is ``distribution``'s checkout.

    Fail-safe: any failure mode (no cwd, no git, not a repo, name
    mismatch) returns ``None`` — the caller falls through to the next
    resolution rule. ``git rev-parse --show-toplevel`` resolves the
    LINKED worktree's own root when run inside one, which is exactly the
    tree a worktree-based agent means.
    """
    # Deferred imports: `_project._discovery` imports this module at top
    # level for `dist_names_match`, so the reverse edge stays lazy.
    from ...linter._new_only import git_repo_root
    from ._project._discovery import _looks_like_checkout_of

    if cwd is None:
        try:
            cwd = Path.cwd()
        except OSError:
            # CWD unlinked underneath us.
            return None
    root = git_repo_root(cwd)
    if root is None:
        return None
    root = root.resolve()
    return root if _looks_like_checkout_of(root, distribution) else None


def resolve_target_tree(
    distribution: str,
    explicit_path: str | Path | None = None,
    *,
    cwd: Path | None = None,
    registry: dict | None = None,
) -> tuple[Path | None, str | None]:
    """Resolve the tree to audit for ``distribution``; deterministic.

    Returns ``(path, rule)`` where ``rule`` is ``"explicit"`` /
    ``"cwd"`` / ``"registry"`` (see module docstring), or
    ``(None, None)`` when none of the three rules answers — the caller
    then falls back to its legacy import-location resolution.

    ``registry`` defaults to the live ``ECOSYSTEM`` mapping; tests
    inject a plain dict (real data, no mocks).
    """
    if explicit_path is not None:
        return Path(explicit_path).expanduser().resolve(), "explicit"
    root = cwd_checkout_of(distribution, cwd=cwd)
    if root is not None:
        return root, "cwd"
    if registry is None:
        from ..._ecosystem import ECOSYSTEM as registry
    local = registry.get(distribution, {}).get("local_path")
    if local:
        cand = Path(local).expanduser()
        if cand.is_dir():
            return cand.resolve(), "registry"
    return None, None


__all__ = [
    "cwd_checkout_of",
    "dist_names_match",
    "normalize_dist_name",
    "resolve_target_tree",
]
