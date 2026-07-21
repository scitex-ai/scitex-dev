"""Surface the RESOLVED checkout being audited — anti wrong-tree footgun.

An audit that silently grades the WRONG tree — a stale editable install, a
sibling checkout resolved by NAME, the ``~/proj/<pkg>`` development guess
(see ``_discovery._resolve_repo_root`` steps 3-4) — reports a confident
pass/fail about a commit it never read. A green "no violations" for a tree
that is not your work is a footgun precisely because nobody double-checks a
clean result.

Before ANY results, the auditor announces the ABSOLUTE resolved path plus
the git branch and short HEAD sha of the tree it is about to grade, so the
operator can catch a wrong-tree resolution at a glance instead of trusting
a green that isn't about their commit.

Fail-safe by contract: git resolution NEVER raises and never blocks the
audit. A tree with no git (sdist extract, tarball) still gets its absolute
filesystem path surfaced; ``branch`` / ``head`` are simply ``None``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .._emit import emit


def _git(repo_root: Path, *args: str) -> str | None:
    """Run ``git -C <repo_root> <args>`` fail-safe; return stdout or None.

    None on every failure mode — git missing, not a checkout, non-zero
    exit, timeout, OSError — so the caller never has to guard.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        out = subprocess.run(
            [git, "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    val = out.stdout.strip()
    return val or None


def resolved_context(repo_root: Path | None) -> dict[str, str | None]:
    """Return ``{resolved_path, branch, head}`` for ``repo_root`` (fail-safe).

    ``resolved_path`` is the ABSOLUTE checkout path (``None`` only when the
    repo could not be located at all). ``branch`` / ``head`` come from git
    and are ``None`` whenever git is unavailable, the tree is not a git
    checkout, or the call fails — never raising, never blocking the audit.
    """
    if repo_root is None:
        return {"resolved_path": None, "branch": None, "head": None}
    return {
        "resolved_path": str(repo_root),
        "branch": _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git(repo_root, "rev-parse", "--short", "HEAD"),
    }


def surface_resolved_tree(
    distribution: str,
    ctx: dict[str, str | None],
    json_out: bool,
    via: str | None = None,
) -> None:
    """Announce the resolved tree at INFO, BEFORE any audit results.

    ``via`` names WHICH resolution rule picked the tree (``explicit`` /
    ``cwd`` / ``registry`` / ``import`` / ``proj-guess`` — see
    ``.._target_tree`` and ``._discovery._resolve_repo_root_with_rule``),
    so a wrong-tree surprise is diagnosable from the banner alone.

    Human rail only: no-op when ``json_out`` is set (the machine payload
    carries the same fields plus ``resolved_via``) and no-op when the
    path could not be resolved (the caller prints its own 'cannot locate
    repo' error then).
    """
    if json_out:
        return
    path = ctx.get("resolved_path")
    if not path:
        return
    branch = ctx.get("branch") or "?"
    head = ctx.get("head") or "?"
    via_txt = f", via {via}" if via else ""
    emit(
        "info",
        f"{distribution}: auditing {path} (branch {branch}, HEAD {head}{via_txt})",
    )
