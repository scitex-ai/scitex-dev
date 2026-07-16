"""Repo / package discovery helpers for the project-structure auditor.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path


def _import_name(distribution: str) -> str:
    """Mirror sibling auditors: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _resolve_repo_root(distribution: str, repo: Path | None) -> Path | None:
    """Return the repo root Path or None if it can't be located.

    If `repo` is given, it's used directly (resolved to an absolute path).
    Otherwise we resolve the package via `importlib.util.find_spec` and walk
    up to the repo root (assumed to contain `pyproject.toml`). Falls back to
    None.

    The explicit `repo` is ``.resolve()``d so the whole audit run operates on
    an absolute root. A *relative* ``--path`` (e.g. ``--path .`` from a
    worktree) would otherwise mix with the absolute paths produced by
    ``fd``-backed file discovery and crash ``Path.relative_to(...)`` in the
    PS-204 orphan-test hinter (see ``_check_orphan_hint.build_orphan_hinter``).
    """
    if repo is not None:
        return repo.resolve()
    import importlib.util

    spec = importlib.util.find_spec(_import_name(distribution))
    if spec is None or not spec.submodule_search_locations:
        return None
    for loc in spec.submodule_search_locations:
        # src/<pkg>/__init__.py → walk up two levels for src layout
        candidate = Path(loc).parent.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate
        # flat layout fallback
        candidate = Path(loc).parent
        if (candidate / "pyproject.toml").is_file():
            return candidate

    # The module is in site-packages and we cannot walk up to a repo root.
    #
    # We used to GUESS here: try ``~/proj/<distribution>``, then scan every
    # directory under ``/home`` for ``<user>/proj/<distribution>``, and audit
    # whichever matched first. That is a silent substitution of a DIFFERENT
    # TREE for the one the caller asked about, and on 2026-07-14 it produced a
    # CI verdict about the wrong code:
    #
    #   PR #691 (scitex-agent-container) changed exactly one thing — it renamed
    #   a test file. Its CI reported a PS-204 violation AT THE OLD NAME, under
    #   /data/gpfs/.../scitex-agent-container. A tree cannot hold the new name
    #   and report the old one, so the auditor was never reading the PR: on the
    #   runner, ~/proj/<name> is a symlink into the shared GPFS checkout. The
    #   gate failed a clean PR, and would equally have passed a dirty one.
    #
    # A resolver that answers with the wrong tree is worse than one that
    # answers "I don't know", because the caller cannot tell the difference.
    # If we cannot locate the repo from the package itself, say so and let the
    # caller fail loudly or pass ``--path`` explicitly.
    return None


def _src_pkg_dir(repo: Path, distribution: str) -> Path | None:
    """Return `src/<pkg>/` if it exists, else None."""
    candidate = repo / "src" / _import_name(distribution)
    return candidate if candidate.is_dir() else None


def _tests_root(repo: Path) -> Path | None:
    candidate = repo / "tests"
    return candidate if candidate.is_dir() else None


def _has_py(d: Path) -> bool:
    """True iff this dir has at least one .py file (excluding __init__)."""
    if not d.is_dir():
        return False
    for child in d.iterdir():
        if child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
            return True
    return False


def _is_git_ignored(path: Path, repo: Path) -> bool:
    """True iff `path` is gitignored relative to `repo`.

    Returns False when git is unavailable or the path isn't inside a git
    repo — non-git checkouts (sdist installs, tarball extracts) still
    get full PS-202 coverage. Used to skip src subdirs that exist locally
    but won't ship in the wheel (e.g. src/<pkg>/app/ if it's listed in
    .gitignore as a developer-only scratch area).
    """
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None or not (repo / ".git").exists():
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(repo), "check-ignore", "--quiet", str(path)],
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    # check-ignore exits 0 when the path IS ignored, 1 when it isn't,
    # 128 on any other error. Only treat exit 0 as "ignored".
    return result.returncode == 0
