# -*- coding: utf-8 -*-
"""Tests for `_check_hard_dep_overreach.py` (PS-149).

Inverse of PS-148: a peer that lists a heavy/niche lib under HARD
`[project.dependencies]` but imports it ONLY in a feature / non-core part
of `src/` over-pulls on every minimal install — the dep should be optional.
Framework deps the public/CLI/MCP surface needs stay HARD and must NOT be
flagged. Each test builds a REAL temp package directory (no mocks) with a
`pyproject` plus source files, then asserts whether PS-149 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_hard_dep_overreach import (
    _heavy_hard_dist_roots,
    _is_core_surface,
    check_ps149_hard_dep_overreach,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_pkg(
    repo: Path,
    *,
    hard_deps: list[str],
    files: dict[str, str],
    dist: str = "scitex-fakepeer",
) -> None:
    """Materialize a real temp package: pyproject + given src files.

    ``files`` maps a path relative to ``src/<import_name>/`` to its body.
    """
    import_name = dist.replace("-", "_")
    deps_lit = "[" + ", ".join(f'"{d}"' for d in hard_deps) + "]"
    _write(
        repo / "pyproject.toml",
        f'[project]\nname = "{dist}"\ndependencies = {deps_lit}\n',
    )
    pkg_dir = repo / "src" / import_name
    for rel, body in files.items():
        _write(pkg_dir / rel, body)


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- helper-level unit checks -----------------------------------------------


def test_heavy_hard_roots_includes_heavy_hard_dep():
    # Arrange
    meta = {"project": {"dependencies": ["torch>=2.0", "numpy"]}}
    # Act
    roots = _heavy_hard_dist_roots(meta)
    # Assert
    assert "torch" in roots


def test_heavy_hard_roots_excludes_light_hard_dep():
    # Arrange
    meta = {"project": {"dependencies": ["numpy>=1.21", "requests"]}}
    # Act
    roots = _heavy_hard_dist_roots(meta)
    # Assert
    assert roots == {}


def test_heavy_hard_roots_excludes_framework_dep_click():
    # Arrange — click is heavy-ish but a CLI's public framework
    meta = {"project": {"dependencies": ["click>=8.0"]}}
    # Act
    roots = _heavy_hard_dist_roots(meta)
    # Assert
    assert roots == {}


def test_heavy_hard_roots_excludes_framework_dep_fastmcp():
    # Arrange — fastmcp is the MCP server's framework
    meta = {"project": {"dependencies": ["fastmcp>=2.0"]}}
    # Act
    roots = _heavy_hard_dist_roots(meta)
    # Assert
    assert roots == {}


def test_heavy_hard_roots_ignores_optional_deps_block():
    # Arrange — torch declared optional, not hard
    meta = {"project": {"optional-dependencies": {"torch": ["torch>=2.0"]}}}
    # Act
    roots = _heavy_hard_dist_roots(meta)
    # Assert
    assert roots == {}


def test_core_surface_true_for_init_file():
    # Arrange
    parts = ("__init__.py",)
    # Act
    result = _is_core_surface(parts)
    # Assert
    assert result is True


def test_core_surface_true_for_cli_dir_module():
    # Arrange
    parts = ("_cli", "_root.py")
    # Act
    result = _is_core_surface(parts)
    # Assert
    assert result is True


def test_core_surface_true_for_mcp_server_file():
    # Arrange
    parts = ("_mcp_server.py",)
    # Act
    result = _is_core_surface(parts)
    # Assert
    assert result is True


def test_core_surface_false_for_feature_module():
    # Arrange
    parts = ("auto", "_decision_tree.py")
    # Act
    result = _is_core_surface(parts)
    # Assert
    assert result is False


# --- PS-149 fires (positive cases) ------------------------------------------


def test_ps149_fires_for_heavy_hard_dep_used_feature_only(tmp_path):
    # Arrange — figrecipe HARD, imported only in a feature helper
    _make_pkg(
        tmp_path,
        hard_deps=["figrecipe>=0.28.0", "numpy"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_plot_helpers.py": (
                "from __future__ import annotations\nimport figrecipe\n"
            ),
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-149" in _codes(out)


def test_ps149_fires_for_torch_used_only_in_feature_module(tmp_path):
    # Arrange — torch HARD, imported only in a deep feature module
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "nn/_model.py": "from __future__ import annotations\nimport torch\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-149" in _codes(out)


def test_ps149_fires_for_function_scoped_feature_import(tmp_path):
    # Arrange — even a lazy import in a feature module proves feature-only use
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_feature.py": (
                "from __future__ import annotations\n"
                "def go():\n    import torch\n    return torch\n"
            ),
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-149" in _codes(out)


def test_ps149_detail_names_the_offending_dist(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        hard_deps=["figrecipe>=0.28.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_plot.py": "from __future__ import annotations\nimport figrecipe\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "figrecipe" in out[0].detail


def test_ps149_detail_names_the_feature_site(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "nn/_model.py": "from __future__ import annotations\nimport torch\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "nn/_model.py" in out[0].where


# --- PS-149 silent (negative cases) -----------------------------------------


def test_ps149_silent_when_heavy_dep_used_in_init(tmp_path):
    # Arrange — figrecipe is genuinely re-exported by the public surface
    _make_pkg(
        tmp_path,
        hard_deps=["figrecipe>=0.28.0"],
        files={
            "__init__.py": ("from __future__ import annotations\nimport figrecipe\n"),
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_when_heavy_dep_used_in_cli(tmp_path):
    # Arrange — torch imported by the CLI entry → genuinely needed → keep HARD
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_cli/_root.py": "from __future__ import annotations\nimport torch\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_when_heavy_dep_used_in_mcp_server(tmp_path):
    # Arrange — fastmcp-class lib imported by the MCP server entry → keep HARD
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_mcp_server.py": "from __future__ import annotations\nimport torch\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_for_framework_dep_click(tmp_path):
    # Arrange — click is the CLI framework; never flagged even feature-only
    _make_pkg(
        tmp_path,
        hard_deps=["click>=8.0"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_helper.py": "from __future__ import annotations\nimport click\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_for_light_hard_dep_numpy(tmp_path):
    # Arrange — numpy is light/ubiquitous; never a candidate
    _make_pkg(
        tmp_path,
        hard_deps=["numpy>=1.21"],
        files={
            "__init__.py": "from __future__ import annotations\n",
            "_calc.py": "from __future__ import annotations\nimport numpy\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_for_dead_hard_dep_never_imported(tmp_path):
    # Arrange — torch declared HARD but never imported (dead dep; other rule)
    _make_pkg(
        tmp_path,
        hard_deps=["torch>=2.0"],
        files={"__init__.py": "from __future__ import annotations\n"},
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_when_dep_is_optional_not_hard(tmp_path):
    # Arrange — torch declared optional + used feature-only is PS-148's job
    import_name = "scitex_fakepeer"
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-fakepeer"\ndependencies = ["numpy"]\n'
        '[project.optional-dependencies]\ntorch = ["torch>=2.0"]\n',
    )
    pkg = tmp_path / "src" / import_name
    _write(pkg / "__init__.py", "from __future__ import annotations\n")
    _write(pkg / "_feature.py", "from __future__ import annotations\nimport torch\n")
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_when_used_in_both_core_and_feature(tmp_path):
    # Arrange — used in __init__ AND a feature module → core wins → keep HARD
    _make_pkg(
        tmp_path,
        hard_deps=["figrecipe>=0.28.0"],
        files={
            "__init__.py": ("from __future__ import annotations\nimport figrecipe\n"),
            "_plot.py": "from __future__ import annotations\nimport figrecipe\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_when_pyproject_absent(tmp_path):
    # Arrange — empty repo, no pyproject
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


# EOF
