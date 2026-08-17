# -*- coding: utf-8 -*-
"""Tests for `_check_umbrella_dep_and_integration.py` (PS-139 / PS-140).

PS-139 bans leaf/standalone packages from listing `scitex` (the umbrella)
in their dependencies. The umbrella *itself* is exempt — its recursive
`scitex[<extra>]` self-references in `pyproject.toml` are how `[all]`
aggregates every peer extra (the documented umbrella-passthrough pattern),
not "umbrella drag."

The exemption used to compare `repo.resolve()` against the ECOSYSTEM
`local_path` with **exact path equality**. That breaks for every git
worktree (`<repo>/.worktrees/<name>`), which is exactly how agents and the
operator run the audit — so PS-139/PS-140 fired ~77 false positives on the
umbrella's own self-extras. These tests pin the three exemption signals:
registry path, main-worktree resolution, and the `[project].name == "scitex"`
backstop. Real temp packages and real `git worktree` checkouts — no mocks.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_umbrella_dep_and_integration import (
    _is_umbrella,
    _main_worktree_root,
    _own_import_name,
    _pyproject_distribution_name,
    check_ps139_umbrella_dep,
    check_ps140_integration_gate,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_git_repo(repo: Path, *, name: str, body: str | None = None) -> None:
    """Materialize a real committed git repo with a pyproject `[project].name`."""
    repo.mkdir(parents=True, exist_ok=True)
    _write(
        repo / "pyproject.toml",
        body if body is not None else f'[project]\nname = "{name}"\n',
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


# --- _pyproject_distribution_name -------------------------------------------


def test_pyproject_distribution_name_reads_project_name(tmp_path):
    # Arrange
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex-foo"\n')
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name == "scitex-foo"


def test_pyproject_distribution_name_none_when_file_absent(tmp_path):
    # Arrange — empty dir, no pyproject
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name is None


def test_pyproject_distribution_name_none_when_name_missing(tmp_path):
    # Arrange — pyproject without a [project].name
    _write(tmp_path / "pyproject.toml", "[build-system]\nrequires = []\n")
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name is None


# --- _main_worktree_root ----------------------------------------------------


def test_main_worktree_root_of_main_checkout_is_itself(tmp_path):
    # Arrange — a plain git repo (no linked worktrees)
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    # Act
    root = _main_worktree_root(repo)
    # Assert
    assert root is not None and root.resolve() == repo.resolve()


def test_main_worktree_root_of_linked_worktree_points_to_main(tmp_path):
    # Arrange — main repo + a linked worktree under .worktrees/
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    root = _main_worktree_root(wt)
    # Assert
    assert root is not None and root.resolve() == repo.resolve()


def test_main_worktree_root_none_outside_git(tmp_path):
    # Arrange — a bare directory, not a git checkout
    # Act
    root = _main_worktree_root(tmp_path)
    # Assert
    assert root is None


# --- _is_umbrella -----------------------------------------------------------


def test_is_umbrella_true_via_pyproject_name(tmp_path):
    # Arrange — `[project].name == "scitex"` is the path-independent backstop
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex"\n')
    # Act
    result = _is_umbrella(tmp_path)
    # Assert
    assert result is True


def test_is_umbrella_true_for_worktree_of_umbrella(tmp_path):
    # Arrange — a linked worktree whose main checkout's pyproject is `scitex`.
    # This is the regression the fix targets: the worktree path differs from
    # the registered local_path, but the main working tree resolves to the
    # umbrella, so the exemption must still fire.
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    result = _is_umbrella(wt)
    # Assert
    assert result is True


def test_is_umbrella_false_for_leaf_package(tmp_path):
    # Arrange — a normal standalone peer
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex-io"\n')
    # Act
    result = _is_umbrella(tmp_path)
    # Assert
    assert result is False


def test_is_umbrella_false_for_worktree_of_leaf(tmp_path):
    # Arrange — worktree of a *leaf* repo must stay non-umbrella (the fix must
    # not over-match every worktree to the umbrella).
    repo = tmp_path / "scitex-io"
    _make_git_repo(repo, name="scitex-io")
    wt = repo / ".worktrees" / "feature"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    result = _is_umbrella(wt)
    # Assert
    assert result is False


# --- PS-139 integration: fires for leaf, silent for umbrella ----------------


def test_ps139_fires_for_leaf_depending_on_umbrella_extra(tmp_path):
    # Arrange — a leaf peer that lists `scitex[io]` (real umbrella drag)
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-foo"\n'
        '[project.optional-dependencies]\nx = ["scitex[io]>=2.0"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-139" in _codes(out)


def test_ps139_fires_for_leaf_with_hard_umbrella_dep(tmp_path):
    # Arrange — leaf with a HARD runtime dep on the umbrella
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-bar"\ndependencies = ["scitex>=2.0", "numpy"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-139" in _codes(out)


def test_ps139_silent_for_umbrella_self_extras_via_pyproject_name(tmp_path):
    # Arrange — the umbrella aggregating its own extras (the legit pattern).
    # `[project].name == "scitex"` makes the exemption fire even off-registry.
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex"\n'
        "[project.optional-dependencies]\n"
        'all = ["scitex[io]", "scitex[plt]", "scitex[stats]"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps139_silent_for_umbrella_worktree_self_extras(tmp_path):
    # Arrange — the exact failing scenario: audit the umbrella from a linked
    # worktree. Self-extras must NOT be flagged (was ~76 false positives).
    repo = tmp_path / "scitex-python"
    _make_git_repo(
        repo,
        name="scitex",
        body=(
            '[project]\nname = "scitex"\n'
            "[project.optional-dependencies]\n"
            'all = ["scitex[io]", "scitex[plt]"]\nrng = ["scitex[repro]"]\n'
        ),
    )
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    out: list = []
    # Act
    check_ps139_umbrella_dep(wt, _StubViolation, out)
    # Assert
    assert out == []


def test_ps139_silent_when_no_umbrella_dep(tmp_path):
    # Arrange — leaf with only third-party deps
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-baz"\ndependencies = ["numpy", "pandas"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert out == []



# --- _own_import_name: canonical name, worktree-dir-name independent --------


def test_own_import_name_prefers_pyproject_distribution_name(tmp_path):
    # Arrange -- checkout dir name differs from the declared distribution name,
    # exactly as in a `<repo>/.worktrees/<pkg>-<suffix>` release worktree.
    repo = tmp_path / "scitex-dev-rel"
    _write(repo / "pyproject.toml", '[project]\nname = "scitex-dev"\n')
    # Act
    own = _own_import_name(repo)
    # Assert -- canonical import name, NOT the dir-derived "scitex_dev_rel".
    assert own == "scitex_dev"


def test_own_import_name_falls_back_to_dir_when_no_pyproject(tmp_path):
    # Arrange -- no pyproject; dir name is the only signal.
    repo = tmp_path / "scitex-foo"
    repo.mkdir()
    # Act
    own = _own_import_name(repo)
    # Assert
    assert own == "scitex_foo"


# --- PS-140 gate: own modules must not be flagged from a suffixed worktree --


def test_ps140_does_not_flag_own_modules_from_suffixed_worktree(tmp_path):
    # Arrange -- a leaf whose source imports BOTH a real peer (scitex_config)
    # and its OWN sub-packages, audited from a worktree whose directory name
    # ("scitex-foo-rel") does not match the distribution name ("scitex-foo").
    # Regression: deriving the own-name from the dir gave "scitex_foo_rel", so
    # the package's own `scitex_foo.*` imports leaked into the cross-package set
    # and fired bogus PS-140 "missing from gate" errors.
    repo = tmp_path / "scitex-foo-rel"
    src = repo / "src" / "scitex_foo"
    src.mkdir(parents=True)
    _write(repo / "pyproject.toml", '[project]\nname = "scitex-foo"\n')
    _write(src / "__init__.py", "")
    _write(
        src / "_core.py",
        "from scitex_foo import _helper\n"
        "from scitex_config import load\n",
    )
    _write(src / "_helper.py", "VALUE = 1\n")
    # The gate lists ONLY the true cross-package import (the peer).
    gate = repo / "tests" / "integration" / "test_cross_package_imports.py"
    _write(
        gate,
        "CROSS_PACKAGE_IMPORTS = [\n    \"scitex_config\",\n]\n",
    )
    out: list = []
    # Act
    check_ps140_integration_gate(repo, "scitex-foo", _StubViolation, out)
    # Assert -- own modules excluded -> the gate already matches -> no violation.
    assert out == []


def test_ps140_still_flags_genuinely_missing_peer_from_suffixed_worktree(tmp_path):
    # Arrange -- same suffixed-worktree shape, but the gate is missing a REAL
    # cross-package peer. The fix must not silence genuine PS-140 violations.
    repo = tmp_path / "scitex-bar-wt"
    src = repo / "src" / "scitex_bar"
    src.mkdir(parents=True)
    _write(repo / "pyproject.toml", '[project]\nname = "scitex-bar"\n')
    _write(src / "__init__.py", "")
    _write(
        src / "_core.py",
        "from scitex_bar import _x\n"
        "from scitex_config import load\n"
        "from scitex_logging import getLogger\n",
    )
    _write(src / "_x.py", "Y = 2\n")
    # Gate omits scitex_logging -> genuinely missing.
    gate = repo / "tests" / "integration" / "test_cross_package_imports.py"
    _write(
        gate,
        "CROSS_PACKAGE_IMPORTS = [\n    \"scitex_config\",\n]\n",
    )
    out: list = []
    # Act
    check_ps140_integration_gate(repo, "scitex-bar", _StubViolation, out)
    # Assert -- the missing peer (not the own module) is reported.
    assert "PS-140" in _codes(out) and any(
        "scitex_logging" in v.detail for v in out
    )


def test_ps140_drift_finding_names_a_runnable_verb(tmp_path):
    """The remedy must be a command, not an instruction to find one.

    This finding read "Regenerate the gate." and named nothing, while the
    deployed files credited `ecosystem write-integration-tests`, which has
    never existed. Between the two, 17 gates went unmaintained: the only
    documented way out was a dead end, so following the instructions
    correctly got you nowhere. Section 2 -- an error that only states what
    broke is half-written.
    """
    # Arrange -- a gate that omits a real peer, so the drift branch fires.
    repo = tmp_path / "scitex-baz"
    src = repo / "src" / "scitex_baz"
    src.mkdir(parents=True)
    _write(repo / "pyproject.toml", '[project]\nname = "scitex-baz"\n')
    _write(src / "__init__.py", "")
    _write(src / "_core.py", "from scitex_config import load\n")
    gate = repo / "tests" / "integration" / "test_cross_package_imports.py"
    _write(gate, "CROSS_PACKAGE_IMPORTS = [\n]\n")
    out: list = []
    # Act
    check_ps140_integration_gate(repo, "scitex-baz", _StubViolation, out)
    # Assert
    assert any("install-cross-package-gate scitex-baz" in v.detail for v in out)


def test_ps140_missing_gate_finding_names_a_runnable_verb(tmp_path):
    """The other PS-140 branch was equally silent about what to run."""
    # Arrange -- cross-package imports present, gate file absent entirely.
    repo = tmp_path / "scitex-qux"
    src = repo / "src" / "scitex_qux"
    src.mkdir(parents=True)
    _write(repo / "pyproject.toml", '[project]\nname = "scitex-qux"\n')
    _write(src / "__init__.py", "")
    _write(src / "_core.py", "from scitex_config import load\n")
    out: list = []
    # Act
    check_ps140_integration_gate(repo, "scitex-qux", _StubViolation, out)
    # Assert
    assert any("install-cross-package-gate scitex-qux" in v.detail for v in out)


# EOF
