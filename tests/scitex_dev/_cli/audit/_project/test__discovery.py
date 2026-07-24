"""Tests for `_cli.audit._project._discovery._resolve_repo_root`.

The wrong-tree class (sac's P0 report): `audit-all` with no `--path`
resolved the tree to audit by IMPORT LOCATION or a `~/proj/<name>`
development guess. Both answer "where is a checkout of this
distribution on this disk?", not "which tree am I running against" — so
on a CI runner the gate graded whatever tree happened to be on disk and
reported a confident pass/fail about a commit it never read.

`_resolve_repo_root` now prefers the CWD's git-root when that root looks
like the target distribution's checkout, which is the tree a test run is
by construction executing against.

PA-306 no-mocks: real `git init`-ed temp checkouts and a real `os.chdir`
with save/restore — no `monkeypatch`, no patched `find_spec`. The
fallback assertions deliberately run against the REAL installed
scitex-dev, because "the install location still wins when there is no
git root" is the actual back-compat contract.

PA-307 test-quality: canonical `# Arrange` / `# Act` / `# Assert`
markers and a single assertion per test.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _chdir(target: Path):
    """`os.chdir` to `target`, restoring the previous CWD on exit."""
    previous = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(previous)


def _make_git_checkout(root: Path, distribution: str) -> Path:
    """Create a real git repo that looks like `distribution`'s checkout.

    A `git init` is enough — `rev-parse --show-toplevel` resolves on an
    empty repo, so no commit (and no user.name/user.email config) is
    needed.
    """
    import_name = distribution.replace("-", "_")
    pkg = root / "src" / import_name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{distribution}"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(root), "init"],
        capture_output=True,
        check=True,
    )
    return root


# ---------------------------------------------------------------------------
# (b) The CWD's git-root is preferred over the install-location guess.
# ---------------------------------------------------------------------------


def test_resolve_repo_root_prefers_cwd_git_root_over_install_location(tmp_path):
    """A checkout under the CWD wins over where scitex-dev is installed.

    This is the CI bug in miniature: `scitex-dev` IS importable here, so
    the find_spec walk would resolve to the installed tree. The commit
    under test is the one the CWD is inside.
    """
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    checkout = _make_git_checkout(tmp_path / "wt", "scitex-dev")
    # Act
    with _chdir(checkout):
        resolved = _resolve_repo_root("scitex-dev", None)
    # Assert
    assert resolved == checkout.resolve()


def test_resolve_repo_root_prefers_cwd_git_root_from_a_subdirectory(tmp_path):
    """Resolution works from anywhere INSIDE the checkout, not just its root."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    checkout = _make_git_checkout(tmp_path / "wt", "scitex-dev")
    # Act
    with _chdir(checkout / "src" / "scitex_dev"):
        resolved = _resolve_repo_root("scitex-dev", None)
    # Assert
    assert resolved == checkout.resolve()


def test_resolve_repo_root_prefers_cwd_git_root_for_worktree_dir_name(tmp_path):
    """A worktree dir named for the BRANCH still resolves via its layout.

    Guards the `_looks_like_checkout_of` layout evidence: a git worktree
    is named `.worktrees/<branch>`, never `<distribution>`, so a
    directory-name-only check would miss exactly the case agents hit.
    """
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    checkout = _make_git_checkout(tmp_path / "feat-some-branch", "scitex-dev")
    # Act
    with _chdir(checkout):
        resolved = _resolve_repo_root("scitex-dev", None)
    # Assert
    assert resolved == checkout.resolve()


def test_resolve_repo_root_ignores_git_root_of_a_different_distribution(tmp_path):
    """A git root that is someone ELSE's checkout must not be hijacked.

    Running `audit-all scitex-io` from inside the scitex-dev tree must
    not grade scitex-dev and call it scitex-io — that would trade one
    wrong-tree bug for a louder one.
    """
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    unrelated = _make_git_checkout(tmp_path / "wt", "some-other-distribution")
    # Act
    with _chdir(unrelated):
        resolved = _resolve_repo_root("scitex-dev", None)
    # Assert
    assert resolved != unrelated.resolve()


def test_resolve_repo_root_explicit_repo_still_wins_over_cwd_git_root(tmp_path):
    """An explicit `--path` outranks the CWD git-root (order step 1 vs 2)."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    explicit = _make_git_checkout(tmp_path / "explicit", "scitex-dev")
    cwd_checkout = _make_git_checkout(tmp_path / "cwd", "scitex-dev")
    # Act
    with _chdir(cwd_checkout):
        resolved = _resolve_repo_root("scitex-dev", explicit)
    # Assert
    assert resolved == explicit.resolve()


# ---------------------------------------------------------------------------
# (c) Fallback: no git root → the historical resolution still answers.
# ---------------------------------------------------------------------------


def test_resolve_repo_root_falls_back_to_install_location_outside_a_git_repo(
    tmp_path,
):
    """Outside any git repo the install/`~/proj` resolution still resolves.

    The back-compat half: preferring the git-root must not have removed
    the old answer, only demoted it. `scitex-dev` is importable in the
    test venv, so a non-None result here IS the fallback firing.
    """
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    outside = tmp_path / "not-a-git-repo"
    outside.mkdir()
    # Act
    with _chdir(outside):
        resolved = _resolve_repo_root("scitex-dev", None)
    # Assert
    assert resolved is not None


def test_resolve_repo_root_returns_none_for_unresolvable_distribution(tmp_path):
    """No git root, not importable, no `~/proj` checkout → None."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _resolve_repo_root

    outside = tmp_path / "not-a-git-repo"
    outside.mkdir()
    # Act
    with _chdir(outside):
        resolved = _resolve_repo_root("scitex-no-such-distribution-xyz", None)
    # Assert
    assert resolved is None


# ---------------------------------------------------------------------------
# `_looks_like_checkout_of` — the guard on the git-root preference.
# ---------------------------------------------------------------------------


def test_looks_like_checkout_of_accepts_declared_project_name(tmp_path):
    """A matching `[project] name` is accepted."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _looks_like_checkout_of

    checkout = _make_git_checkout(tmp_path / "wt", "scitex-io")
    # Act
    verdict = _looks_like_checkout_of(checkout, "scitex-io")
    # Assert
    assert verdict is True


def test_looks_like_checkout_of_rejects_disagreeing_project_name(tmp_path):
    """A pyproject that declares a DIFFERENT name is a hard no."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _looks_like_checkout_of

    checkout = _make_git_checkout(tmp_path / "wt", "scitex-io")
    # Act
    verdict = _looks_like_checkout_of(checkout, "scitex-stats")
    # Assert
    assert verdict is False


def test_looks_like_checkout_of_rejects_tree_without_pyproject(tmp_path):
    """No pyproject.toml → not a checkout of anything auditable."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _looks_like_checkout_of

    bare = tmp_path / "bare"
    bare.mkdir()
    # Act
    verdict = _looks_like_checkout_of(bare, "scitex-io")
    # Assert
    assert verdict is False


def test_looks_like_checkout_of_accepts_pep503_name_variant(tmp_path):
    """A declared `Scitex_IO` IS a checkout of `scitex-io` (PEP-503 fold)."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _looks_like_checkout_of

    checkout = tmp_path / "wt"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "Scitex_IO"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    # Act
    verdict = _looks_like_checkout_of(checkout, "scitex-io")
    # Assert
    assert verdict is True


def test_looks_like_checkout_of_accepts_src_layout_without_declared_name(tmp_path):
    """With no parseable `[project] name`, `src/<pkg>/` is enough evidence."""
    # Arrange
    from scitex_dev._cli.audit._project._discovery import _looks_like_checkout_of

    checkout = tmp_path / "wt"
    (checkout / "src" / "scitex_io").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        "[build-system]\nrequires = []\n", encoding="utf-8"
    )
    # Act
    verdict = _looks_like_checkout_of(checkout, "scitex-io")
    # Assert
    assert verdict is True
