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
    _has_thin_reexport_init,
    _heavy_hard_dist_roots,
    _is_core_surface,
    _is_umbrella_package,
    _registry_umbrella_dists,
    check_ps149_hard_dep_overreach,
    find_module_imports,
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


# ============================================================================
# #173 Bug 1 — find_module_imports replaces buggy regex-based counters.
# One assertion per shape so a regression points at the exact missing shape.
# ============================================================================


def test_find_module_imports_bare_top_level_import():
    # Arrange — `import numpy`
    src = "import numpy\n"
    # Act
    hits = find_module_imports(src, {"numpy"})
    # Assert
    assert "numpy" in hits


def test_find_module_imports_aliased_top_level_import():
    # Arrange — `import pandas as pd` (the shape `\b`-regex with `as` boundary missed)
    src = "import pandas as pd\n"
    # Act
    hits = find_module_imports(src, {"pandas"})
    # Assert
    assert "pandas" in hits


def test_find_module_imports_dotted_top_level_import():
    # Arrange — `import numpy.fft` counts as a hit for `numpy`
    src = "import numpy.fft\n"
    # Act
    hits = find_module_imports(src, {"numpy"})
    # Assert
    assert "numpy" in hits


def test_find_module_imports_from_simple():
    # Arrange — `from scipy import signal`
    src = "from scipy import signal\n"
    # Act
    hits = find_module_imports(src, {"scipy"})
    # Assert
    assert "scipy" in hits


def test_find_module_imports_from_dotted():
    # Arrange — `from scipy.stats import ttest_ind`
    src = "from scipy.stats import ttest_ind\n"
    # Act
    hits = find_module_imports(src, {"scipy"})
    # Assert
    assert "scipy" in hits


def test_find_module_imports_function_scoped():
    # Arrange — lazy import inside a function body (regex with `^\\s*` missed this)
    src = "def f():\n    import h5py\n    return h5py\n"
    # Act
    hits = find_module_imports(src, {"h5py"})
    # Assert
    assert "h5py" in hits


def test_find_module_imports_method_scoped():
    # Arrange — `from pandas.api import types` inside a method
    src = (
        "class C:\n"
        "    def m(self):\n"
        "        from pandas.api import types\n"
        "        return types\n"
    )
    # Act
    hits = find_module_imports(src, {"pandas"})
    # Assert
    assert "pandas" in hits


def test_find_module_imports_ignores_relative_imports():
    # Arrange — `from .sib import X` is first-party, never a third-party hit
    src = "from .sibling import helper\n"
    # Act
    hits = find_module_imports(src, {"sibling"})
    # Assert
    assert hits == set()


def test_find_module_imports_ignores_comments_and_strings():
    # Arrange — only literal `import` statements count; comments/strings do not
    src = '# import numpy here later\nx = "import pandas"\nimport scipy\n'
    # Act
    hits = find_module_imports(src, {"numpy", "pandas", "scipy"})
    # Assert
    assert hits == {"scipy"}


def test_find_module_imports_ignores_uncandidate_roots():
    # Arrange — only the requested roots are counted (no over-reporting)
    src = "import numpy\nimport pandas\n"
    # Act
    hits = find_module_imports(src, {"numpy"})
    # Assert
    assert hits == {"numpy"}


def test_find_module_imports_handles_unparseable_text():
    # Arrange — broken source returns empty set rather than crashing the audit
    src = "def f(:\n  pass\n"
    # Act
    hits = find_module_imports(src, {"numpy"})
    # Assert
    assert hits == set()


def test_find_module_imports_empty_candidate_set_short_circuits():
    # Arrange — no candidates → empty result, no AST parsing required
    src = "import numpy\n"
    # Act
    hits = find_module_imports(src, set())
    # Assert
    assert hits == set()


def test_find_module_imports_fixture_every_shape_in_one_file():
    # Arrange — single fixture exercising every shape the bare `\\b`-regex
    # missed (Bug 1). Acts as a regression sentinel: if the AST detector
    # ever loses a shape this single test pinpoints it via the set diff.
    src = (
        "import numpy\n"
        "import pandas as pd\n"
        "import numpy.fft\n"
        "from scipy import signal\n"
        "from scipy.stats import ttest_ind\n"
        "def f():\n"
        "    import h5py\n"
        "    from numpy import linalg\n"
        "class C:\n"
        "    def m(self):\n"
        "        from pandas.api import types\n"
        "# import biopython mentioned in a comment — must not count\n"
        'doc = "import vaex in a string — must not count"\n'
    )
    # Act
    hits = find_module_imports(src, {"numpy", "pandas", "scipy", "h5py"})
    # Assert
    assert hits == {"numpy", "pandas", "scipy", "h5py"}


# ============================================================================
# #173 Bug 2 — umbrella packages (`scitex` and aliases) declare HARD core
# deps as a user contract. PS-149 must not flag them as overreach. The
# heuristic and registry paths are exercised independently.
# ============================================================================


def test_registry_umbrella_dists_includes_scitex():
    # Arrange — registry tags `scitex` as the umbrella
    # Act
    dists = _registry_umbrella_dists()
    # Assert
    assert "scitex" in dists


def test_is_umbrella_package_via_registry_name(tmp_path):
    # Arrange — `[project].name = "scitex"` (the registry-tagged umbrella)
    meta = {"project": {"name": "scitex", "dependencies": ["numpy"]}}
    pkg_root = tmp_path / "src" / "scitex"
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text("from __future__ import annotations\n")
    # Act
    result = _is_umbrella_package(meta, pkg_root)
    # Assert
    assert result is True


def test_is_umbrella_package_registry_lookup_is_case_insensitive(tmp_path):
    # Arrange — pyproject `name = "SciTeX"` (capitalisation drift). Registry
    # is normalised lower-case so this still resolves to the umbrella.
    meta = {"project": {"name": "SciTeX", "dependencies": ["numpy"]}}
    pkg_root = tmp_path / "src" / "scitex"
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text("\n")
    # Act
    result = _is_umbrella_package(meta, pkg_root)
    # Assert
    assert result is True


def test_is_umbrella_package_via_thin_reexport_heuristic(tmp_path):
    # Arrange — distribution NOT in the registry, but __init__ is a thin
    # re-export shim with no implementation siblings (catches scitex-code
    # / future umbrella aliases per #173).
    meta = {"project": {"name": "scitex-code", "dependencies": ["torch>=2.0"]}}
    pkg_root = tmp_path / "src" / "scitex_code"
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text(
        '"""scitex-code: alias re-export of scitex-python."""\n'
        "from __future__ import annotations\n"
        "from scitex import *  # noqa: F401,F403\n"
        '__all__ = ["__version__"]\n'
        '__version__ = "0.0.0"\n'
    )
    # Act
    result = _is_umbrella_package(meta, pkg_root)
    # Assert
    assert result is True


def test_is_umbrella_package_false_for_normal_package(tmp_path):
    # Arrange — regular package: real impl module + meaningful __init__
    meta = {"project": {"name": "scitex-stats", "dependencies": ["torch>=2.0"]}}
    pkg_root = tmp_path / "src" / "scitex_stats"
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text(
        "from __future__ import annotations\nfrom ._impl import compute\n"
    )
    (pkg_root / "_impl.py").write_text("def compute():\n    return 42\n")
    # Act
    result = _is_umbrella_package(meta, pkg_root)
    # Assert
    assert result is False


def test_has_thin_reexport_init_true_for_pure_reexport(tmp_path):
    # Arrange
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        '"""thin reexport"""\nfrom __future__ import annotations\nfrom x import y\n'
    )
    # Act
    result = _has_thin_reexport_init(pkg)
    # Assert
    assert result is True


def test_has_thin_reexport_init_false_when_impl_sibling_present(tmp_path):
    # Arrange — sibling implementation module disqualifies the heuristic
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from .impl import foo\n")
    (pkg / "impl.py").write_text("def foo():\n    return 1\n")
    # Act
    result = _has_thin_reexport_init(pkg)
    # Assert
    assert result is False


def test_has_thin_reexport_init_false_when_init_defines_function(tmp_path):
    # Arrange — __init__ that defines code (not just re-exports) is not thin
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def helper():\n    return 1\n")
    # Act
    result = _has_thin_reexport_init(pkg)
    # Assert
    assert result is False


def test_has_thin_reexport_init_allows_underscore_internal_siblings(tmp_path):
    # Arrange — `_version.py` / `_lazy.py` style internals are allowed
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from __future__ import annotations\nfrom ._version import __version__\n"
    )
    (pkg / "_version.py").write_text('__version__ = "0.1.0"\n')
    # Act
    result = _has_thin_reexport_init(pkg)
    # Assert
    assert result is True


def test_ps149_silent_for_umbrella_with_heavy_hard_dep(tmp_path):
    # Arrange — `scitex` umbrella declaring `torch` HARD with zero imports.
    # Without the umbrella skip, PS-149 would fire (heavy + dead-of-core).
    # With it, the umbrella's user-contract dep is preserved.
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex"\ndependencies = ["torch>=2.0"]\n',
    )
    pkg = tmp_path / "src" / "scitex"
    _write(pkg / "__init__.py", "from __future__ import annotations\n")
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_silent_for_umbrella_alias_via_heuristic(tmp_path):
    # Arrange — `scitex-code` (not yet registry-tagged) detected via the
    # thin-reexport fallback. Should not flag even with a heavy HARD dep.
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-code"\ndependencies = ["torch>=2.0"]\n',
    )
    pkg = tmp_path / "src" / "scitex_code"
    _write(
        pkg / "__init__.py",
        "from __future__ import annotations\nfrom scitex import *  # noqa: F401,F403\n",
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-code", _StubViolation, out)
    # Assert
    assert out == []


def test_ps149_still_fires_for_non_umbrella_after_umbrella_skip(tmp_path):
    # Arrange — regression guard: the umbrella skip must NOT swallow normal
    # packages. A regular peer with figrecipe HARD + feature-only use still
    # gets PS-149.
    _make_pkg(
        tmp_path,
        hard_deps=["figrecipe>=0.28.0"],
        files={
            "__init__.py": "from __future__ import annotations\nfrom ._impl import x\n",
            "_impl.py": "def x():\n    return 1\n",
            "_plot.py": "from __future__ import annotations\nimport figrecipe\n",
        },
    )
    out: list = []
    # Act
    check_ps149_hard_dep_overreach(tmp_path, "scitex-fakepeer", _StubViolation, out)
    # Assert
    assert "PS-149" in _codes(out)


# EOF
