# -*- coding: utf-8 -*-
"""Tests for `_check_optional_deps_guarded.py` (PS-148).

A peer that lists a heavy third-party lib under
`[project.optional-dependencies]` must guard the corresponding import in
`src/` so `import <peer>` succeeds with only core deps installed. Each
test builds a REAL temp package directory (no mocks) with a `pyproject`
plus a source file, then asserts whether PS-148 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_optional_deps_guarded import (
    _import_roots_for,
    _optional_lib_roots,
    check_ps148_optional_deps_guarded,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _make_pkg(
    repo: Path,
    *,
    optional_deps: dict[str, list[str]],
    src_body: str,
    dist: str = "scitex-fakepeer",
) -> None:
    """Materialize a real temp package: pyproject + src/<pkg>/__init__.py."""
    import_name = dist.replace("-", "_")
    extras = "\n".join(
        f"{name} = {deps!r}".replace("'", '"') for name, deps in optional_deps.items()
    )
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{dist}"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        f"{extras}\n",
        encoding="utf-8",
    )
    pkg_dir = repo / "src" / import_name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(src_body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- helper-level unit checks -----------------------------------------------


def test_import_roots_maps_known_dist_aliases():
    # Arrange
    dist = "scikit-learn"
    # Act
    roots = _import_roots_for(dist)
    # Assert
    assert "sklearn" in roots


def test_import_roots_falls_back_to_underscore_form():
    # Arrange
    dist = "some-unknown-lib"
    # Act
    roots = _import_roots_for(dist)
    # Assert
    assert "some_unknown_lib" in roots


def test_optional_lib_roots_skips_dev_extra():
    # Arrange
    meta = {
        "project": {
            "optional-dependencies": {
                "dev": ["pytest", "ruff"],
                "torch": ["torch>=2.0"],
            }
        }
    }
    # Act
    roots = _optional_lib_roots(meta)
    # Assert
    assert "pytest" not in roots


def test_optional_lib_roots_skips_scitex_peer_deps():
    # Arrange
    meta = {"project": {"optional-dependencies": {"clew": ["scitex-clew>=0.2"]}}}
    # Act
    roots = _optional_lib_roots(meta)
    # Assert
    assert roots == {}


# --- PS-148 fires (positive cases) ------------------------------------------


def test_ps148_fires_on_unguarded_top_level_import(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        optional_deps={"torch": ["torch>=2.0"]},
        src_body="from __future__ import annotations\nimport torch\n",
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-148" in _codes(out)


def test_ps148_fires_on_unguarded_from_import(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        optional_deps={"pandas": ["pandas>=2.0"]},
        src_body="from __future__ import annotations\nfrom pandas import DataFrame\n",
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-148" in _codes(out)


def test_ps148_fires_via_dist_alias_import_root(tmp_path):
    # Arrange — declared as `pillow`, imported as `PIL`
    _make_pkg(
        tmp_path,
        optional_deps={"image": ["pillow>=10"]},
        src_body="from __future__ import annotations\nimport PIL\n",
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-148" in _codes(out)


def test_ps148_detail_names_the_offending_dist(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        optional_deps={"torch": ["torch>=2.0"]},
        src_body="from __future__ import annotations\nimport torch\n",
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "torch" in out[0].detail


# --- PS-148 silent (negative cases) -----------------------------------------


def test_ps148_silent_when_import_guarded_by_try_except(tmp_path):
    # Arrange
    _make_pkg(
        tmp_path,
        optional_deps={"torch": ["torch>=2.0"]},
        src_body=(
            "from __future__ import annotations\n"
            "try:\n    import torch\nexcept ImportError:\n    torch = None\n"
        ),
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps148_silent_when_import_is_function_scoped(tmp_path):
    # Arrange — lazy import never fires on bare `import <peer>`
    _make_pkg(
        tmp_path,
        optional_deps={"torch": ["torch>=2.0"]},
        src_body=(
            "from __future__ import annotations\n"
            "def use_torch():\n    import torch\n    return torch\n"
        ),
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps148_silent_when_no_optional_extras_declared(tmp_path):
    # Arrange — torch is a hard dep here, not optional
    repo = tmp_path
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-fakepeer"\ndependencies = ["torch", "numpy"]\n',
        encoding="utf-8",
    )
    pkg_dir = repo / "src" / "scitex_fakepeer"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(
        "from __future__ import annotations\nimport torch\n", encoding="utf-8"
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(repo, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps148_silent_for_dunder_main_block_import(tmp_path):
    # Arrange — import inside `if __name__ == "__main__":` never runs on import
    _make_pkg(
        tmp_path,
        optional_deps={"torch": ["torch>=2.0"]},
        src_body=(
            "from __future__ import annotations\n"
            'if __name__ == "__main__":\n    import torch\n    print(torch)\n'
        ),
    )
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps148_silent_when_pyproject_absent(tmp_path):
    # Arrange — empty repo, no pyproject
    out: list = []
    # Act
    check_ps148_optional_deps_guarded(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert out == []


# EOF
