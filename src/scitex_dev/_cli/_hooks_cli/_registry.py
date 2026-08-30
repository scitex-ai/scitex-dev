"""Canonical-hook registry + symlink-status helpers.

Data layer for every leaf in the ``hooks`` click group.
:data:`KNOWN_HOOKS` is the single source of truth for "what hooks does
scitex-dev ship and where do they deploy?" — adding a new canonical hook
is a single dict entry here plus a one-line accessor in
``scitex_dev._hooks.__init__``.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from ... import _hooks

# Map: canonical name → (source path, deploy-relative path).
# A SYMLINK is created at <project>/<deploy_rel> pointing at the source.
# When a future canonical hook lands, add it here.
#
# The deploy_rel for ``pre_push`` is ``.githooks/pre-push`` (no ``.sh``
# suffix — git's pre-push contract is filename-based: the binary must be
# named exactly ``pre-push``). The bundled source keeps its ``.sh``
# suffix for editor/syntax parity with the other shipped hooks; the
# symlink renames it at deploy time.
KNOWN_HOOKS: dict[str, tuple[str, str]] = {
    "run_lint": (
        _hooks.run_lint_sh_path(),
        "docs/to_claude/hooks/post-tool-use/run_lint.sh",
    ),
    # run_testmon is the PRE-PUSH test selector — the warm-cache wrapper
    # that pre-push.sh Step 4 calls (resolved via `hooks show-path
    # run_testmon`). It is deliberately NOT a `.pre-commit-config.yaml`
    # entry: a test selector belongs at pre-push, not pre-commit (a test
    # suite at commit time is banned by PS-HOOK-001 /
    # 15_pre-commit-policy.md). The deploy_rel therefore lives under
    # `pre-push/`, not `pre-commit/`.
    "run_testmon": (
        _hooks.run_testmon_sh_path(),
        "docs/to_claude/hooks/pre-push/run_testmon.sh",
    ),
    "pre_push": (
        _hooks.pre_push_sh_path(),
        ".githooks/pre-push",
    ),
    # The LOCAL-`main`-is-a-mirror guard. Same filename-based contract as
    # `pre_push`: git looks for a file named exactly `pre-commit`, so the
    # symlink drops the `.sh` the source keeps. Like `pre_push` it is
    # INERT until `core.hooksPath` points at `.githooks`, which is why it
    # has its own `enable-pre-commit` leaf rather than relying on plain
    # `hooks install` — a guard that is installed and never fires is
    # worse than one that is absent, because the absence is visible.
    "pre_commit": (
        _hooks.pre_commit_sh_path(),
        ".githooks/pre-commit",
    ),
    # The merge gate: refuses `gh pr merge` unless `scitex-dev ci verify`
    # returns READY. Registered here so `hooks install` deploys it like any
    # other canonical hook -- the ORIGINAL copy of this script was an
    # untracked file in one container and was lost outright (2026-08-16),
    # which is why it now ships from the package AND deploys by symlink
    # rather than by someone remembering to copy it.
    "require_mergeable_verdict": (
        _hooks.require_mergeable_verdict_sh_path(),
        "docs/to_claude/hooks/pre-tool-use/require_mergeable_verdict.sh",
    ),
}


def _is_symlink_to(symlink: Path, target_abs: str) -> bool:
    """True if ``symlink`` is a symlink resolving to ``target_abs``."""
    if not symlink.is_symlink():
        return False
    try:
        return os.path.realpath(str(symlink)) == os.path.realpath(target_abs)
    except OSError:
        return False


def _install_one(
    name: str,
    source: str,
    deploy_rel: str,
    project: Path,
    force: bool,
) -> str:
    """Install one canonical hook into ``project``. Returns a status word.

    Status words (printed by the CLI in coloured form):
    ``installed``  — created a fresh symlink
    ``updated``    — re-pointed an existing symlink to the current source
    ``up-to-date`` — symlink already points at the canonical (no-op)
    ``refused``    — non-symlink file present, ``--force`` not given
    ``forced``     — overwrote a non-symlink file under ``--force``
    """
    del name  # reserved for future per-hook policy hooks
    target = project / deploy_rel
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() or target.is_symlink():
        if _is_symlink_to(target, source):
            return "up-to-date"
        if target.is_symlink():
            # Stale or out-of-date symlink — always safe to replace.
            target.unlink()
            target.symlink_to(source)
            return "updated"
        # Real file (not a symlink).
        if not force:
            return "refused"
        target.unlink()
        target.symlink_to(source)
        return "forced"

    target.symlink_to(source)
    return "installed"


def _list_one(name: str, source: str, deploy_rel: str, project: Path) -> str:
    """Report the install status of one hook in ``project`` as a status word.

    ``ok``       — points at the canonical
    ``drift``    — file present but NOT the canonical (real file or
                   symlink to elsewhere)
    ``stale``    — symlink present but broken / source missing
    ``missing``  — not installed
    """
    del name  # reserved for future per-hook policy hooks
    target = project / deploy_rel
    if not target.exists() and not target.is_symlink():
        return "missing"
    if target.is_symlink():
        if not target.exists():
            return "stale"
        if _is_symlink_to(target, source):
            return "ok"
        return "drift"
    return "drift"


def install_symbol(status: str) -> str:
    """Coloured status word for the install / update / enable surfaces."""
    return {
        "installed": click.style("installed ", fg="green"),
        "updated": click.style("updated   ", fg="green"),
        "up-to-date": click.style("up-to-date", fg="cyan"),
        "refused": click.style("refused   ", fg="red"),
        "forced": click.style("forced    ", fg="yellow"),
    }.get(status, status)


__all__ = [
    "KNOWN_HOOKS",
    "_is_symlink_to",
    "_install_one",
    "_list_one",
    "install_symbol",
]
