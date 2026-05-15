"""Tests for scitex_dev._branding._audit (PS-2xx rules, real registry).

No mocks: exercises the actual auditor against synthesized package layouts
under tmp_path and the shipped ``registry.yaml``.
"""

from __future__ import annotations

from scitex_dev._branding._audit import (
    audit_brand_package,
    audit_local_brand_glue,
    audit_registry_consistency,
)


def test_shipped_registry_is_self_consistent():
    # Arrange
    # (no setup — audits the real registry.yaml)
    # Act
    violations = audit_registry_consistency()
    # Assert
    assert violations == []


def test_audit_local_glue_detects_local_get_env_in_branding_module(tmp_path):
    # Arrange: _branding.py that re-implements get_env (replaced by central helper)
    pkg = tmp_path / "socialia"
    src = pkg / "src" / "socialia"
    src.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project]\nname='socialia'\n")
    (src / "_branding.py").write_text(
        "def get_env(key, default=None):\n    return None\n"
    )
    # Act
    files = {v.get("file") for v in audit_local_brand_glue(pkg, "socialia")}
    # Assert
    assert "src/socialia/_branding.py" in files


def test_audit_local_glue_ignores_branding_module_with_only_text_utils(tmp_path):
    # Arrange: _branding.py with only docstring text-rebranding is allowed.
    pkg = tmp_path / "figrecipe"
    src = pkg / "src" / "figrecipe"
    src.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project]\nname='figrecipe'\n")
    (src / "_branding.py").write_text("def rebrand_text(s):\n    return s\n")
    # Act
    violations = audit_local_brand_glue(pkg, "figrecipe")
    # Assert
    assert violations == []


def test_audit_local_glue_detects_brand_alias_setattr_loop(tmp_path):
    # Arrange
    pkg = tmp_path / "figrecipe"
    src = pkg / "src" / "figrecipe"
    src.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project]\nname='figrecipe'\n")
    (src / "evil.py").write_text(
        "for _s in ('a','b'):\n    setattr(C, f'{_BRAND_ALIAS}_{_s}', None)\n"
    )
    # Act
    files = {v.get("file") for v in audit_local_brand_glue(pkg, "figrecipe")}
    # Assert
    assert "src/figrecipe/evil.py" in files


def test_audit_local_glue_clean(tmp_path):
    # Arrange
    pkg = tmp_path / "figrecipe"
    src = pkg / "src" / "figrecipe"
    src.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project]\nname='figrecipe'\n")
    (src / "__init__.py").write_text("# clean\n")
    # Act
    violations = audit_local_brand_glue(pkg, "figrecipe")
    # Assert
    assert violations == []


def test_audit_brand_package_clean_for_empty_socialia_layout(tmp_path):
    # Arrange
    pkg = tmp_path / "socialia"
    src = pkg / "src" / "socialia"
    src.mkdir(parents=True)
    (pkg / "pyproject.toml").write_text("[project]\nname='socialia'\n")
    (src / "__init__.py").write_text("")
    # Act
    violations = audit_brand_package(pkg, "socialia")
    # Assert
    assert violations == []
