"""Tests for scitex_dev._release.pypi_package_data."""

from __future__ import annotations

import textwrap
import zipfile
from pathlib import Path


from scitex_dev._release.pypi_package_data import (
    _list_src_data_files,
    _detect_backend,
    _has_package_data_block,
    _suggest_fix,
    audit_package_data,
)


def _make_pkg(tmp_path: Path, *, with_data_block: bool = True) -> Path:
    """Build a minimal setuptools package with a data file."""
    root = tmp_path / "demo-pkg"
    (root / "src" / "demo_pkg" / "_skills").mkdir(parents=True)
    (root / "src" / "demo_pkg" / "__init__.py").write_text("")
    (root / "src" / "demo_pkg" / "_skills" / "SKILL.md").write_text("# skill\n")
    pkg_data = (
        '[tool.setuptools.package-data]\ndemo_pkg = ["_skills/**/*.md"]\n'
        if with_data_block
        else ""
    )
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [build-system]
            requires = ["setuptools>=68.0", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "demo-pkg"
            version = "0.0.1"
            requires-python = ">=3.9"

            [tool.setuptools.packages.find]
            where = ["src"]

            {pkg_data}
            """
        ).lstrip()
    )
    return root


def test_list_src_data_files_includes_md_excludes_py_demo_pkg__skills_skill_md_in_rels(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path)
    (root / "src" / "demo_pkg" / "code.py").write_text("x = 1\n")
    files = _list_src_data_files(root)
    rels = {str(p) for p in files}
    assert "demo_pkg/_skills/SKILL.md" in rels


def test_list_src_data_files_includes_md_excludes_py_not_any_p_suffix_py_for_p_in_files(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path)
    (root / "src" / "demo_pkg" / "code.py").write_text("x = 1\n")
    files = _list_src_data_files(root)
    rels = {str(p) for p in files}
    assert not any(p.suffix == ".py" for p in files)


def test_list_src_data_files_skips_egg_info(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path)
    egg = root / "src" / "demo_pkg.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("Name: demo\n")
    files = _list_src_data_files(root)
    assert not any("egg-info" in part for p in files for part in p.parts)


def test_detect_backend_setuptools(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path)
    assert _detect_backend(root / "pyproject.toml") == "setuptools.build_meta"


def test_has_package_data_block_setuptools_has_package_data_block_root_pyproject_to(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=True)
    assert _has_package_data_block(root / "pyproject.toml", "setuptools.build_meta")
    root2 = _make_pkg(tmp_path / "alt", with_data_block=False)


def test_has_package_data_block_setuptools_not__has_package_data_block_root2_pyproj(tmp_path: Path) -> None:
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=True)
    root2 = _make_pkg(tmp_path / "alt", with_data_block=False)
    assert not _has_package_data_block(
        root2 / "pyproject.toml", "setuptools.build_meta"
    )


def test_suggest_fix_setuptools_emits_quoted_globs_tool_setuptools_package_data_in_snippet() -> None:
    # Arrange
    # Act
    # Assert
    snippet = _suggest_fix("setuptools.build_meta", "demo_pkg", ["_skills/SKILL.md"])
    assert "[tool.setuptools.package-data]" in snippet


def test_suggest_fix_setuptools_emits_quoted_globs_skills_skill_md_in_snippet() -> None:
    # Arrange
    # Act
    # Assert
    snippet = _suggest_fix("setuptools.build_meta", "demo_pkg", ["_skills/SKILL.md"])
    assert '"_skills/SKILL.md"' in snippet


def test_suggest_fix_returns_empty_when_no_missing() -> None:
    # Arrange
    # Act
    # Assert
    assert _suggest_fix("setuptools.build_meta", "demo_pkg", []) == ""


def test_audit_with_explicit_wheel_clean_r_is_clean(tmp_path: Path) -> None:
    """Build a wheel ourselves and audit against it. Clean case: data file
    declared in package-data and shipped."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=True)
    # Synthesize a wheel containing the SKILL.md
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        z.writestr("demo_pkg/_skills/SKILL.md", "# skill\n")
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert r.is_clean


def test_audit_with_explicit_wheel_clean_r_missing_in_wheel(tmp_path: Path) -> None:
    """Build a wheel ourselves and audit against it. Clean case: data file
    declared in package-data and shipped."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=True)
    # Synthesize a wheel containing the SKILL.md
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        z.writestr("demo_pkg/_skills/SKILL.md", "# skill\n")
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert r.missing_in_wheel == []


def test_audit_with_explicit_wheel_clean_demo_pkg__skills_skill_md_in_str_p_for_p(tmp_path: Path) -> None:
    """Build a wheel ourselves and audit against it. Clean case: data file
    declared in package-data and shipped."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=True)
    # Synthesize a wheel containing the SKILL.md
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        z.writestr("demo_pkg/_skills/SKILL.md", "# skill\n")
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert "demo_pkg/_skills/SKILL.md" in [str(p) for p in r.src_data_files]


def test_audit_detects_missing_data_file_not_r_is_clean(tmp_path: Path) -> None:
    """Wheel built without package-data: SKILL.md missing → audit flags it."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=False)
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        # SKILL.md deliberately omitted
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert not r.is_clean


def test_audit_detects_missing_data_file_any_skill_md_in_str_p_for_p_in_r_missing(tmp_path: Path) -> None:
    """Wheel built without package-data: SKILL.md missing → audit flags it."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=False)
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        # SKILL.md deliberately omitted
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert any("SKILL.md" in str(p) for p in r.missing_in_wheel)


def test_audit_detects_missing_data_file_tool_setuptools_package_data_in_r_fix_su(tmp_path: Path) -> None:
    """Wheel built without package-data: SKILL.md missing → audit flags it."""
    # Arrange
    # Act
    # Assert
    root = _make_pkg(tmp_path, with_data_block=False)
    wheel = tmp_path / "demo_pkg-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("demo_pkg/__init__.py", "")
        # SKILL.md deliberately omitted
        z.writestr("demo_pkg-0.0.1.dist-info/METADATA", "Name: demo-pkg\n")
        z.writestr("demo_pkg-0.0.1.dist-info/RECORD", "")
    r = audit_package_data(root, wheel_path=wheel, keep_wheel=True)
    assert "[tool.setuptools.package-data]" in r.fix_suggestion
