#!/usr/bin/env python3
"""The generated audit gate must pin the tree it is supposed to grade.

Two defects, one root cause (scitex-storage vs scitex-dev v0.38.1):

1. `install-audit-gate` (and its `write-audit-test` alias) emitted
   `audit_all_for_package("<pkg>")` with NO `path=` — the exact shape
   `audit_all_for_package`'s own docstring calls "a compatibility shim,
   not a recommendation". It happens to work on CI, where the cwd IS the
   checkout, and grades the PARENT repo when pytest runs from a worktree.

2. The docstring's example uses `parents[1]`, correct for
   `tests/test_audit.py`. The generator writes
   `tests/develop/test_audit.py` — one level deeper — so a copied
   `parents[1]` resolves to `tests/` and the audit grades a
   SUBDIRECTORY as if it were the package.

Every assertion below is on the RESOLVED PATH, never on the literal N:
an assertion on the number would have happily locked in the wrong one.

No mocks (PA-306 / STX-NM002): real tmp_path trees, and the emitted
anchor expression is evaluated against a real `__file__` value.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scitex_dev._cli.ecosystem._cmds._install_gate import (
    anchor_depth,
    render_audit_gate,
)

GATE_RELPATH = ("tests", "develop", "test_audit.py")


def _emitted_anchor(source: str, gate_file: Path) -> Path:
    """Resolve the `path=` expression the generator emitted, for real.

    Parses the generated module, finds the `path=` keyword of the
    `audit_all_for_package(...)` call, and evaluates that exact
    expression with `__file__` bound to where the gate was written —
    so the test measures what the emitted code DOES, not what it says.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if getattr(fn, "id", None) != "audit_all_for_package":
            continue
        for kw in node.keywords:
            if kw.arg == "path":
                expr = ast.Expression(body=kw.value)
                ast.fix_missing_locations(expr)
                code = compile(expr, "<emitted-anchor>", "eval")
                return eval(code, {"Path": Path, "__file__": str(gate_file)})
    raise AssertionError("generated gate passes no `path=` to audit_all_for_package")


@pytest.fixture
def package_root(tmp_path):
    """A package checkout with the gate's directory materialised."""
    root = tmp_path / "scitex-storage"
    (root / "tests" / "develop").mkdir(parents=True)
    return root


@pytest.fixture
def gate_file(package_root):
    """Where `install-audit-gate` writes the gate."""
    return package_root.joinpath(*GATE_RELPATH)


@pytest.fixture
def gate_source(package_root, gate_file):
    """The generated gate, written to disk exactly as the command does."""
    source = render_audit_gate("scitex-storage", gate_file, package_root)
    gate_file.write_text(source, encoding="utf-8")
    return source


class TestGeneratedGatePinsThePackageRoot:
    """The emitted anchor must resolve to the package root itself."""

    def test_emitted_anchor_resolves_to_the_package_root(
        self, package_root, gate_file, gate_source
    ):
        """THE BUG: `parents[1]` here would resolve to `tests/`."""
        # Arrange
        expected = package_root.resolve()
        # Act
        resolved = _emitted_anchor(gate_source, gate_file)
        # Assert
        assert resolved == expected

    def test_emitted_anchor_is_not_the_tests_subdirectory(
        self, package_root, gate_file, gate_source
    ):
        """Negative control for the exact wrong answer storage hit."""
        # Arrange
        wrong = (package_root / "tests").resolve()
        # Act
        resolved = _emitted_anchor(gate_source, gate_file)
        # Assert
        assert resolved != wrong

    def test_generated_gate_names_the_distribution(self, gate_source):
        """Positive control: pinning didn't cost the distribution arg."""
        # Arrange
        expected = "scitex-storage"
        # Act
        rendered = gate_source
        # Assert
        assert expected in rendered

    def test_generated_gate_imports_pathlib(self, gate_source):
        """The emitted anchor needs `Path` in scope to even run."""
        # Arrange
        expected = "from pathlib import Path"
        # Act
        rendered = gate_source
        # Assert
        assert expected in rendered

    def test_generated_gate_is_valid_python(self, gate_source):
        """A gate that does not parse is a gate that never grades."""
        # Arrange
        source = gate_source
        # Act
        parsed = ast.parse(source)
        # Assert
        assert isinstance(parsed, ast.Module)


class TestAnchorDepthIsDerivedNotHardcoded:
    """N follows the depth the file is actually written at."""

    @pytest.mark.parametrize(
        "relparts",
        [
            ("tests", "test_audit.py"),
            ("tests", "develop", "test_audit.py"),
            ("tests", "develop", "audit", "test_audit.py"),
        ],
    )
    def test_anchor_resolves_to_root_at_every_depth(self, tmp_path, relparts):
        """Written deeper, N grows — the resolved root does not move."""
        # Arrange
        root = tmp_path / "pkg"
        target = root.joinpath(*relparts)
        target.parent.mkdir(parents=True)
        source = render_audit_gate("demo-pkg", target, root)
        # Act
        resolved = _emitted_anchor(source, target)
        # Assert
        assert resolved == root.resolve()

    def test_depth_for_the_generators_own_layout(self, tmp_path):
        """`tests/develop/test_audit.py` is two directory levels down."""
        # Arrange
        root = tmp_path / "pkg"
        target = root.joinpath(*GATE_RELPATH)
        target.parent.mkdir(parents=True)
        # Act
        n = anchor_depth(target, root)
        # Assert
        assert target.resolve().parents[n] == root.resolve()
