"""scitex-dev canonical agent hooks (Pillar-0).

The 2026-06-12 ripple-wm dogfood pinned the fanned-out-copy class:
~10 deployed copies of ``run_lint.sh`` across operator projects each
carried their own drift, and the canonical chain of
``scitex-linter`` (archived) + ``scitex linter`` (dropped #95
umbrella-thinning) silently no-op'd the SciTeX pattern check on
every research script edit. This package ships the AUTHORITATIVE
hook scripts so future fixes land in one place and operator projects
that symlink (or thin-wrap) automatically pick them up.

To install in a project (manual today; future ``scitex-dev hooks
install`` CLI will automate this):

    ln -s "$(python -c 'from scitex_dev._hooks import HOOK_DIR; \
        import pathlib; print(pathlib.Path(HOOK_DIR) / "run_lint.sh")')" \
        docs/to_claude/hooks/post-tool-use/run_lint.sh
"""

from __future__ import annotations

import pathlib

HOOK_DIR: str = str(pathlib.Path(__file__).resolve().parent)
"""Absolute path of the directory holding the canonical hook scripts."""


def run_lint_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``run_lint.sh``.

    Used by operator-project bootstrap scripts (and the future
    ``scitex-dev hooks install`` CLI) to resolve the file without
    string-concatenating ``HOOK_DIR``. Always returns the path inside
    the installed scitex-dev package, never a copy.
    """
    return str(pathlib.Path(HOOK_DIR) / "run_lint.sh")


def run_testmon_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``run_testmon.sh``.

    The testmon warm-cache wrapper makes pytest-testmon worktree-
    resilient: every release runs in a FRESH worktree with a COLD
    ``.testmondata``, so testmon re-runs the full suite instead of only
    impacted tests. This wrapper seed-copies a persistent per-(repo,
    pyXY) cache in/out of the worktree. Resolved the same way as
    :func:`run_lint_sh_path` so operator-project bootstrap and the
    ``scitex-dev hooks`` CLI never string-concatenate ``HOOK_DIR``.
    """
    return str(pathlib.Path(HOOK_DIR) / "run_testmon.sh")


def pre_push_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``pre-push.sh``.

    The local pre-push gate runs the SAME audit conformance check CI
    runs (``scitex-dev ecosystem audit-all``) plus a diff-scoped
    ruff/import-smoke/testmon subset BEFORE ``git push``, so the
    operator does not push → CI red → push fix → CI red merry-go-round.
    Resolved the same way as :func:`run_lint_sh_path` so operator-project
    bootstrap and the ``scitex-dev hooks`` CLI never string-concatenate
    ``HOOK_DIR``. Installed (as a symlink named ``pre-push``, no ``.sh``
    suffix — git's pre-push contract is filename-based) via
    ``scitex-dev hooks enable-pre-push --target <repo>``.
    """
    return str(pathlib.Path(HOOK_DIR) / "pre-push.sh")


def pre_commit_sh_path() -> str:
    """Return the absolute filesystem path of the canonical ``pre-commit.sh``.

    The LOCAL-``main``-is-a-mirror guard: it refuses a commit whose HEAD
    is ``main`` or ``master`` and prints the one road that is allowed
    (develop -> topic branch -> PR -> release). It exists because a
    convention was not enough — measured 2026-08-30, ``main`` was ahead
    of ``develop`` in every repository checked, and three release PRs had
    been conflicted for weeks because feature PRs had been merged with
    ``main`` as their base.

    Resolved the same way as :func:`run_lint_sh_path` so nothing
    string-concatenates ``HOOK_DIR``. Installed (as a symlink named
    ``pre-commit``, no ``.sh`` suffix — git's hook contract is
    filename-based) via ``scitex-dev dev hooks enable-pre-commit
    --target <repo>``, which also wires ``core.hooksPath``: without that
    second step a script at ``.githooks/pre-commit`` never runs.
    """
    return str(pathlib.Path(HOOK_DIR) / "pre-commit.sh")


def require_mergeable_verdict_sh_path() -> str:
    """Return the absolute path of the canonical merge-gate hook.

    A pre-tool-use hook that refuses ``gh pr merge`` unless
    ``scitex-dev ci verify`` returns a READY verdict. The operator asked for
    this as a HOOK rather than a prompt (2026-08-09): 「プロンプトとか弱い
    よ? hook とかで強制でしょ?」

    IT LIVES HERE BECAUSE THE FIRST COPY DID NOT. It was originally written
    as an UNTRACKED file in one container's dotfiles checkout, and on
    2026-08-16 it was found GONE -- no git object, no diff, no reflog.
    Measured the same hour: ``scitex-dev ci verify``, the checker it calls,
    was alive and unchanged, because it ships inside this distribution.

        shipped in the package   -> survived a container rebuild
        distributed by file-copy -> lost, silently

    "Silently" is load-bearing: a missing gate does not raise, the guarded
    command simply proceeds, and seven pull requests merged through the gap
    before anyone looked. This is the same fanned-out-copy class named in
    this module's docstring -- the 2026-06-12 ripple-wm case was ten copies
    that DRIFTED; this was one copy that VANISHED. Same cure.

    Shipping it here also removes a version-skew hazard: hook and checker
    are released together, so they can no longer disagree about the exit
    codes in :mod:`scitex_dev.ci._exit_codes`. That disagreement is not
    hypothetical -- on 2026-08-09 it made a GREEN pull request report as
    NOT ready to merge, because exit 2 is Click's usage error and was being
    read as a domain verdict.
    """
    return str(pathlib.Path(HOOK_DIR) / "require_mergeable_verdict.sh")


__all__ = [
    "HOOK_DIR",
    "run_lint_sh_path",
    "run_testmon_sh_path",
    "pre_push_sh_path",
    "pre_commit_sh_path",
    "require_mergeable_verdict_sh_path",
]
