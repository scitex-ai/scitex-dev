"""Canonical-hook registry + symlink-status helpers.

This is the data layer used by every leaf in the ``hooks`` click group.
:data:`KNOWN_HOOKS` is the single source of truth for "what hooks does
scitex-dev ship and where do they deploy?" — adding a new canonical
hook is a single dict entry here plus a one-line accessor in
``scitex_dev._hooks.__init__``.
"""

from __future__ import annotations

import os
from pathlib import Path

from ... import _hooks


# Map: canonical name → (source path, deploy-relative path).
# A SYMLINK is created at <project>/<deploy_rel> pointing at the source.
# When a future canonical hook lands, add it here.
#
# The deploy_rel for ``pre_push`` is ``.githooks/pre-push`` (no ``.sh``
# suffix — git's pre-push contract is filename-based: the binary must
# be named exactly ``pre-push``). The bundled script's filename inside
# scitex-dev keeps the ``.sh`` suffix for editor/syntax-highlighter
# parity with the other shipped hooks; the symlink renames it at
# deploy time.
KNOWN_HOOKS: dict[str, tuple[str, str]] = {
    "run_lint": (
        _hooks.run_lint_sh_path(),
        "docs/to_claude/hooks/post-tool-use/run_lint.sh",
    ),
    "pre_push": (
        _hooks.pre_push_sh_path(),
        ".githooks/pre-push",
    ),
}


def is_symlink_to(symlink: Path, target_abs: str) -> bool:
    """True if ``symlink`` is a symlink resolving to ``target_abs``."""
    if not symlink.is_symlink():
        return False
    try:
        return os.path.realpath(str(symlink)) == os.path.realpath(target_abs)
    except OSError:
        return False


def install_one(
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
        if is_symlink_to(target, source):
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


def list_one(name: str, source: str, deploy_rel: str, project: Path) -> str:
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
        if is_symlink_to(target, source):
            return "ok"
        return "drift"
    return "drift"


__all__ = ["KNOWN_HOOKS", "install_one", "is_symlink_to", "list_one"]
