"""Repo / package discovery helpers for the project-structure auditor.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path

from .._target_tree import dist_names_match


def _import_name(distribution: str) -> str:
    """Mirror sibling auditors: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _pyproject_name(repo: Path) -> str | None:
    """Return the ``[project] name`` declared in ``repo/pyproject.toml``.

    Best-effort by design (mirrors the `tomllib` usage in
    ``_summary/_mcp_parity.py``): returns None on a missing/unparseable
    pyproject, on a `[project]` table with no `name`, and on Python <3.11
    where `tomllib` doesn't exist. Every None sends the caller to the
    layout-evidence fallback rather than to a wrong answer.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(errors="ignore"))
        name = data.get("project", {}).get("name")
        if isinstance(name, str) and name:
            return name
    except Exception:
        pass
    return None


def _looks_like_checkout_of(repo: Path, distribution: str) -> bool:
    """True iff `repo` is plausibly a checkout of `distribution`.

    The guard on the CWD-git-root preference below. Without it, running
    `audit-all scitex-io` from inside the scitex-dev checkout would grade
    scitex-dev's tree and call it scitex-io — trading one wrong-tree bug
    for a louder one.

    Evidence, strongest first:

      1. `pyproject.toml`'s declared `[project] name` — authoritative
         when present. A declared name that DISAGREES is a hard no, not
         a fall-through: a repo that says it is something else is not
         this distribution's checkout, whatever its directory is called.
         Compared PEP-503-normalized (case / `-` / `_` / `.` folded), so
         `Demo_Pkg` IS a checkout of `demo-pkg`.
      2. Layout — `src/<import_name>/` or a flat `<import_name>/__init__.py`.
         This is what carries git WORKTREES, whose directory is named for
         the branch (`.worktrees/feat-x`), not the distribution.
      3. Directory name — last resort, for a checkout with neither a
         parseable name nor a recognisable layout.
    """
    if not (repo / "pyproject.toml").is_file():
        return False
    declared = _pyproject_name(repo)
    if declared is not None:
        return dist_names_match(declared, distribution)
    import_name = _import_name(distribution)
    if (repo / "src" / import_name).is_dir():
        return True
    if (repo / import_name / "__init__.py").is_file():
        return True
    return dist_names_match(repo.name, distribution)


def _cwd_git_root(distribution: str) -> Path | None:
    """Return the CWD's git-root iff it's a checkout of `distribution`.

    Reuses `linter._new_only.git_repo_root` (the codebase's existing
    `git rev-parse --show-toplevel` wrapper) rather than adding a second
    git-root resolver.
    """
    from ....linter._new_only import git_repo_root

    try:
        root = git_repo_root(Path.cwd())
    except OSError:
        # Path.cwd() raises when the CWD has been unlinked underneath us.
        return None
    if root is None:
        return None
    root = root.resolve()
    return root if _looks_like_checkout_of(root, distribution) else None


def _resolve_repo_root_with_rule(
    distribution: str, repo: Path | None
) -> tuple[Path | None, str | None]:
    """Return ``(repo_root, rule)``; ``(None, None)`` if it can't be located.

    ``rule`` names which resolution step picked the tree — ``"explicit"``
    / ``"cwd"`` / ``"import"`` / ``"proj-guess"`` — and is threaded into
    the resolved-tree banner (``via <rule>``) so a wrong-tree resolution
    is diagnosable at a glance.

    Resolution order, first hit wins:

      1. An explicit `repo` (i.e. ``--path``) — always authoritative
         (``explicit``).
      2. The CWD's git-root, when it looks like `distribution`'s checkout
         (see `_looks_like_checkout_of`) (``cwd``).
      3. The installed package's location via `importlib.util.find_spec`,
         walked up to the repo root (assumed to contain `pyproject.toml`)
         (``import``).
      4. A `~/proj/<distribution>` (and `/home/*/proj/<distribution>`)
         development guess (``proj-guess``).
      5. ``(None, None)``.

    Steps 3-4 answer "where is a checkout of this distribution on this
    disk?", which is NOT the question a CI gate is asking — it wants "the
    tree I am running against". The two silently diverge exactly where it
    hurts most: on a runner, an editable install or the `~/proj` guess
    resolves to whatever tree happens to be on disk, so the audit grades
    the wrong source and reports a confident pass/fail about a commit it
    never read. Preferring the CWD's git-root (step 2) closes that gap
    for the common case, because a test run's CWD is inside the checkout
    under test. It is a safety net, not a substitute for step 1: callers
    that know their checkout should pass `--path` and not rely on
    ambient CWD.

    The explicit `repo` is ``.resolve()``d so the whole audit run operates on
    an absolute root. A *relative* ``--path`` (e.g. ``--path .`` from a
    worktree) would otherwise mix with the absolute paths produced by
    ``fd``-backed file discovery and crash ``Path.relative_to(...)`` in the
    PS-204 orphan-test hinter (see ``_check_orphan_hint.build_orphan_hinter``).
    """
    if repo is not None:
        return repo.resolve(), "explicit"
    from_cwd = _cwd_git_root(distribution)
    if from_cwd is not None:
        return from_cwd, "cwd"
    import importlib.util

    spec = importlib.util.find_spec(_import_name(distribution))
    if spec is None or not spec.submodule_search_locations:
        return None, None
    for loc in spec.submodule_search_locations:
        # src/<pkg>/__init__.py → walk up two levels for src layout
        candidate = Path(loc).parent.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate, "import"
        # flat layout fallback
        candidate = Path(loc).parent
        if (candidate / "pyproject.toml").is_file():
            return candidate, "import"

    # Fallback: module is in site-packages (non-editable PyPI install).
    # Try common development checkout locations.
    proj_roots: list[Path] = []
    try:
        home_proj = Path.home() / "proj"
        if home_proj.is_dir():
            proj_roots.append(home_proj)
    except Exception:
        pass
    try:
        for home_dir in Path("/home").iterdir():
            p = home_dir / "proj"
            if p.is_dir() and p not in proj_roots:
                proj_roots.append(p)
    except Exception:
        pass
    for root in proj_roots:
        candidate = root / distribution
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve(), "proj-guess"

    return None, None


def _resolve_repo_root(distribution: str, repo: Path | None) -> Path | None:
    """Back-compat wrapper: `_resolve_repo_root_with_rule` minus the rule."""
    root, _rule = _resolve_repo_root_with_rule(distribution, repo)
    return root


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
