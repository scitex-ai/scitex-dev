"""Tests for `_cli.audit._target_tree` — deterministic target-tree resolution.

Operator directive (2026-07-21): audits must land on the tree the CALLER
meant. Reference incident: on a CI runner, `audit_all_for_package(
'scitex-dev')` with no explicit path resolved the operator's
`~/proj/scitex-dev` develop checkout via the registry's `local_path`
instead of the CI checkout the calling test lived in. The registry
lookup used to outrank the caller's own working tree; `resolve_target_tree`
inverts that: explicit `--path` > current checkout (cwd git toplevel,
including linked worktrees) > registry `local_path`.

PA-306 no-mocks: real `git init` / `git worktree add` temp checkouts and
an injected plain-dict registry (real data, no monkeypatching).
PA-307 test-quality: `# Arrange` / `# Act` / `# Assert` markers, one
assertion per test.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from scitex_dev._cli.audit._target_tree import (
    cwd_checkout_of,
    dist_names_match,
    normalize_dist_name,
    resolve_target_tree,
)


@contextmanager
def _chdir(target: Path):
    """`os.chdir` to `target`, restoring the previous CWD on exit."""
    previous = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(previous)


def _git(*args: str) -> None:
    subprocess.run(
        ["git", *args],
        capture_output=True,
        check=True,
    )


def _make_checkout(
    root: Path, distribution: str, *, declared_name: str | None = None
) -> Path:
    """Create a real committed git repo shaped like `distribution`'s checkout.

    A commit (not just `git init`) so the checkout can host linked
    worktrees via `git worktree add`.
    """
    import_name = distribution.replace("-", "_")
    pkg = root / "src" / import_name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{declared_name or distribution}"\n'
        'version = "0.0.0"\n',
        encoding="utf-8",
    )
    _git("-C", str(root), "init", "-q")
    _git("-C", str(root), "add", "-A")
    _git(
        "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-q", "-m", "init",
    )
    return root


def _add_worktree(main: Path, worktree: Path, branch: str) -> Path:
    """`git worktree add` a linked worktree of `main` at `worktree`."""
    _git("-C", str(main), "worktree", "add", "-q", "-b", branch, str(worktree))
    return worktree


# ---------------------------------------------------------------------------
# normalize_dist_name / dist_names_match — PEP-503 folding
# ---------------------------------------------------------------------------


def test_normalize_dist_name_folds_case_and_separator_runs():
    """Case folds, and every [-_.] run collapses to a single '-'."""
    # Arrange
    # Act
    normalized = normalize_dist_name("Demo__Pkg.x")
    # Assert
    assert normalized == "demo-pkg-x"


def test_dist_names_match_accepts_underscore_hyphen_variants():
    """`Demo_Pkg` and `demo-pkg` name the same distribution."""
    # Arrange
    # Act
    verdict = dist_names_match("Demo_Pkg", "demo-pkg")
    # Assert
    assert verdict is True


# ---------------------------------------------------------------------------
# rule (a): an explicit path ALWAYS wins
# ---------------------------------------------------------------------------


def test_explicit_path_wins_even_when_cwd_is_another_checkout(tmp_path):
    """Rule (a): explicit `--path` outranks a matching cwd checkout."""
    # Arrange
    explicit = _make_checkout(tmp_path / "explicit", "demo-pkg")
    elsewhere = _make_checkout(tmp_path / "elsewhere", "demo-pkg")
    # Act
    resolved, _via = resolve_target_tree(
        "demo-pkg", explicit, cwd=elsewhere, registry={}
    )
    # Assert
    assert resolved == explicit.resolve()


def test_explicit_path_reports_the_explicit_rule(tmp_path):
    """Rule (a) is named `explicit` for the banner."""
    # Arrange
    explicit = _make_checkout(tmp_path / "explicit", "demo-pkg")
    # Act
    _resolved, via = resolve_target_tree("demo-pkg", explicit, registry={})
    # Assert
    assert via == "explicit"


# ---------------------------------------------------------------------------
# rule (b): cwd inside a checkout of the requested distribution
# ---------------------------------------------------------------------------


def test_cwd_inside_main_checkout_resolves_that_checkout(tmp_path):
    """Rule (b): no path + cwd inside the checkout → that checkout."""
    # Arrange
    checkout = _make_checkout(tmp_path / "main", "demo-pkg")
    # Act — cwd is a SUBDIRECTORY, resolution still finds the toplevel.
    resolved, _via = resolve_target_tree(
        "demo-pkg", None, cwd=checkout / "src" / "demo_pkg", registry={}
    )
    # Assert
    assert resolved == checkout.resolve()


def test_cwd_rule_is_named_cwd_for_the_banner(tmp_path):
    """Rule (b) is named `cwd` for the banner."""
    # Arrange
    checkout = _make_checkout(tmp_path / "main", "demo-pkg")
    # Act
    _resolved, via = resolve_target_tree(
        "demo-pkg", None, cwd=checkout, registry={}
    )
    # Assert
    assert via == "cwd"


def test_cwd_defaults_to_the_real_working_directory(tmp_path):
    """Omitting `cwd` uses Path.cwd() (the real invocation shape)."""
    # Arrange
    checkout = _make_checkout(tmp_path / "main", "demo-pkg")
    # Act
    with _chdir(checkout):
        resolved, _via = resolve_target_tree("demo-pkg", None, registry={})
    # Assert
    assert resolved == checkout.resolve()


def test_cwd_inside_linked_worktree_resolves_the_worktree_not_main(tmp_path):
    """Rule (b) in a LINKED worktree targets the worktree's own tree.

    `git rev-parse --show-toplevel` inside a linked worktree returns the
    worktree root, not the main checkout — the tree a worktree-based
    agent means.
    """
    # Arrange
    main = _make_checkout(tmp_path / "main", "demo-pkg")
    worktree = _add_worktree(main, tmp_path / "wt-feat-x", "feat-x")
    # Act
    resolved, _via = resolve_target_tree(
        "demo-pkg", None, cwd=worktree, registry={}
    )
    # Assert
    assert resolved == worktree.resolve()


def test_cwd_worktree_outranks_a_registry_mapping(tmp_path):
    """THE incident in miniature: the registry must NOT outrank the worktree.

    A registry that maps the distribution to a different (develop)
    checkout used to win over the caller's own tree — the CI runner then
    graded the operator's checkout instead of the commit under test.
    """
    # Arrange
    main = _make_checkout(tmp_path / "main", "demo-pkg")
    worktree = _add_worktree(main, tmp_path / "wt-feat-y", "feat-y")
    registry = {"demo-pkg": {"local_path": str(main)}}
    # Act
    resolved, _via = resolve_target_tree(
        "demo-pkg", None, cwd=worktree, registry=registry
    )
    # Assert
    assert resolved == worktree.resolve()


def test_cwd_checkout_matches_pep503_name_variant(tmp_path):
    """A pyproject declaring `Demo_Pkg` IS a checkout of `demo-pkg`."""
    # Arrange
    checkout = _make_checkout(
        tmp_path / "main", "demo-pkg", declared_name="Demo_Pkg"
    )
    # Act
    resolved, _via = resolve_target_tree(
        "demo-pkg", None, cwd=checkout, registry={}
    )
    # Assert
    assert resolved == checkout.resolve()


def test_cwd_checkout_of_rejects_a_different_distributions_tree(tmp_path):
    """A cwd inside someone ELSE's checkout must not be hijacked."""
    # Arrange
    other = _make_checkout(tmp_path / "other", "some-other-dist")
    # Act
    root = cwd_checkout_of("demo-pkg", cwd=other)
    # Assert
    assert root is None


# ---------------------------------------------------------------------------
# rule (c): registry fallback — legitimate for cross-package audits
# ---------------------------------------------------------------------------


def test_unrelated_cwd_falls_back_to_the_registry_local_path(tmp_path):
    """Rule (c): cwd not a matching checkout → registry `local_path`."""
    # Arrange
    reg_checkout = _make_checkout(tmp_path / "registry-tree", "demo-pkg")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    registry = {"demo-pkg": {"local_path": str(reg_checkout)}}
    # Act
    resolved, _via = resolve_target_tree(
        "demo-pkg", None, cwd=unrelated, registry=registry
    )
    # Assert
    assert resolved == reg_checkout.resolve()


def test_registry_rule_is_named_registry_for_the_banner(tmp_path):
    """Rule (c) is named `registry` for the banner."""
    # Arrange
    reg_checkout = _make_checkout(tmp_path / "registry-tree", "demo-pkg")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    registry = {"demo-pkg": {"local_path": str(reg_checkout)}}
    # Act
    _resolved, via = resolve_target_tree(
        "demo-pkg", None, cwd=unrelated, registry=registry
    )
    # Assert
    assert via == "registry"


def test_unresolvable_returns_none_none(tmp_path):
    """No path, no matching cwd, no registry entry → (None, None)."""
    # Arrange
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    # Act
    resolved_pair = resolve_target_tree(
        "demo-pkg", None, cwd=unrelated, registry={}
    )
    # Assert
    assert resolved_pair == (None, None)


def test_registry_local_path_that_is_not_a_dir_is_skipped(tmp_path):
    """A stale registry `local_path` (missing dir) resolves to nothing."""
    # Arrange
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    registry = {"demo-pkg": {"local_path": str(tmp_path / "gone")}}
    # Act
    resolved_pair = resolve_target_tree(
        "demo-pkg", None, cwd=unrelated, registry=registry
    )
    # Assert
    assert resolved_pair == (None, None)
