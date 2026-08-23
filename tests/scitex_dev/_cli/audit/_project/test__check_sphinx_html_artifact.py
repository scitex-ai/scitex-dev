#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS-121 must measure whether the docs reach the WHEEL, not the source tree.

No mocks (STX-NM002): every test builds a real repo layout on a tmp_path and
drives the real `check_sphinx_html`. Nothing patches the filesystem or fakes a
pyproject parse.

Context: on 2026-08-21 PS-121 fired against scitex-cards for a bundle that is
gitignored and generated at release. The published wheel
(scitex_cards-0.48.0-py3-none-any.whl) was opened and contains 100
_sphinx_html entries including index.html — so the rule reported a proxy
(source-tree file) while the property it protects (shipped docs) was true.
"""

from __future__ import annotations

from dataclasses import dataclass

from scitex_dev._cli.audit._project._check_sphinx_html import check_sphinx_html


@dataclass
class _V:
    rule: str
    where: str
    detail: str


def _repo_with_sphinx(tmp_path, pyproject: str = ""):
    """A real repo tree that triggers the PS-121 family (has docs/sphinx)."""
    (tmp_path / "docs" / "sphinx").mkdir(parents=True)
    (tmp_path / "docs" / "sphinx" / "conf.py").write_text("project = 'x'\n")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(pyproject)
    return tmp_path


_WHEEL_ONLY = """
[tool.hatch.build.targets.wheel]
artifacts = ["src/pkg/_sphinx_html/**/*"]
"""

_SDIST_ONLY = """
[tool.hatch.build.targets.sdist]
artifacts = ["src/pkg/_sphinx_html/**/*"]
"""

_BOTH = """
[tool.hatch.build.targets.sdist]
artifacts = ["src/pkg/_sphinx_html/**/*"]

[tool.hatch.build.targets.wheel]
artifacts = ["src/pkg/_sphinx_html/**/*"]
"""


def _ps121(out):
    return [v for v in out if v.rule == "PS-121"]


def test_release_time_bundle_declared_on_the_wheel_satisfies_the_rule():
    """The false positive this fixes: absent from source, present in the wheel."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), _WHEEL_ONLY)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert _ps121(out) == []


def test_declaring_only_on_sdist_is_still_a_finding():
    """The wheel does not inherit sdist artifacts — a shipped defect, not
    a hypothetical. Accepting 'declared on any target' would pass exactly the
    configuration that published a wheel with no docs."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), _SDIST_ONLY)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert len(_ps121(out)) == 1


def test_the_sdist_only_finding_names_the_wheel_target_as_the_fix():
    """A finding must say what to do, and the remedy here is specific."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), _SDIST_ONLY)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert "targets.wheel" in _ps121(out)[0].detail


def test_declaring_on_both_targets_satisfies_the_rule():
    """The correct configuration must stay silent."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), _BOTH)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert _ps121(out) == []


def test_no_bundle_and_no_declaration_still_fires():
    """The rule must keep catching the case it was written for."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), "")
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert len(_ps121(out)) == 1


def test_the_remedy_no_longer_advises_committing_to_a_protected_branch():
    """The old remedy was an operation that cannot succeed on a protected
    default branch, and whose failure reports success."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), "")
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert "protected default" in _ps121(out)[0].detail



# --------------------------------------------------------------------------- #
# PS-128 must read the wheel declaration too, not only the .gitignore          #
# --------------------------------------------------------------------------- #
# Reported by scitex-cards 2026-08-23. #734 taught PS-121 to read the artifacts
# declaration; PS-128 was left behind, so fixing PS-121 alone just moved the
# same "commit the build output" demand one rule over -- and that demand is
# unsatisfiable alongside PS-231's BLOCKER 2, which forbids a leaf from
# vendoring build output back into the tree.

_GITIGNORES_HTML = "build/\nsrc/pkg/_sphinx_html/\n*.pyc\n"


def _ps128(out):
    return [v for v in out if v.rule == "PS-128"]


def test_a_declared_bundle_is_not_a_gitignore_violation():
    """Gitignored AND shipped is exactly what hatchling `artifacts` is for."""
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), _WHEEL_ONLY)
    (repo / ".gitignore").write_text(_GITIGNORES_HTML)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert _ps128(out) == []


def test_an_undeclared_bundle_is_still_a_violation():
    """The control: without the declaration PS-128 must still fire.

    Without this, the fix could have disabled PS-128 outright and the other
    test would still pass.
    """
    # Arrange
    import tempfile
    from pathlib import Path

    repo = _repo_with_sphinx(Path(tempfile.mkdtemp()), "")
    (repo / ".gitignore").write_text(_GITIGNORES_HTML)
    out: list = []
    # Act
    check_sphinx_html(repo, _V, out)
    # Assert
    assert len(_ps128(out)) == 1

# EOF
