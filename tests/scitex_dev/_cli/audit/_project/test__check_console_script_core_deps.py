# -*- coding: utf-8 -*-
"""Tests for `_check_console_script_core_deps.py` (PS-213).

PS-213 fires when a dep is imported at module-load on the reachability
chain rooted at a `[project.scripts]` entry-point, but the dep lives in
`[project.optional-dependencies]` rather than `[project.dependencies]`.
The companion PS-213i info-emission confirms the canonical permitted
lazy-extra pattern (function-scope import + install-hint string
referencing a real extra).

Each test builds a REAL temp package directory (no mocks) — pyproject
plus source files — then asserts whether PS-213 / PS-213i fire. Style:
AAA markers (PA-307 / STX-TQ002), one assertion per test (STX-TQ007).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_console_script_core_deps import (
    check_ps213_console_script_core_deps,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


_DIST = "scitex-fakecli"
_IMPORT_NAME = "scitex_fakecli"


def _write_pyproject(
    repo: Path,
    *,
    dependencies: list[str],
    optional_dependencies: dict[str, list[str]],
    scripts: dict[str, str] | None = None,
) -> None:
    deps = ", ".join(f'"{d}"' for d in dependencies)
    extras_block = ""
    if optional_dependencies:
        rows = "\n".join(
            f"{name} = {deps!r}".replace("'", '"')
            for name, deps in optional_dependencies.items()
        )
        extras_block = f"[project.optional-dependencies]\n{rows}\n"
    scripts_block = ""
    if scripts:
        rows = "\n".join(f'{name} = "{target}"' for name, target in scripts.items())
        scripts_block = f"[project.scripts]\n{rows}\n"
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{_DIST}"\n'
        f"dependencies = [{deps}]\n" + extras_block + scripts_block,
        encoding="utf-8",
    )


def _write_pkg(
    repo: Path,
    *,
    init_body: str = "",
    cli_body: str = "",
) -> None:
    pkg = repo / "src" / _IMPORT_NAME
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(init_body, encoding="utf-8")
    if cli_body:
        (pkg / "_cli.py").write_text(cli_body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- happy paths --------------------------------------------------------------


def test_no_scripts_emits_nothing(tmp_path):
    # Arrange
    _write_pyproject(
        tmp_path,
        dependencies=["click>=8.0"],
        optional_dependencies={},
        scripts=None,
    )
    _write_pkg(tmp_path, init_body="import click\n")
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert out == []


def test_click_in_core_deps_passes(tmp_path):
    # Arrange — click is core, imported at module-load on the entry-point
    # chain → PS-213 must NOT fire.
    _write_pyproject(
        tmp_path,
        dependencies=["click>=8.0"],
        optional_dependencies={},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body="",
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert "PS-213" not in _codes(out)


# --- violation paths ----------------------------------------------------------


def test_click_only_in_extras_with_script_fires_ps213(tmp_path):
    # Arrange — click lives in [cli] extra only; the [project.scripts]
    # entry's module imports click at module-load. This is the canonical
    # violation (scitex-dev's own pre-fix state).
    _write_pyproject(
        tmp_path,
        dependencies=[],
        optional_dependencies={"cli": ["click>=8.0"]},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body="",
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert "PS-213" in _codes(out)


def test_violation_detail_names_the_offending_root(tmp_path):
    # Arrange
    _write_pyproject(
        tmp_path,
        dependencies=[],
        optional_dependencies={"cli": ["click>=8.0"]},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body="",
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    ps213 = [v for v in out if v.rule == "PS-213"]
    # Assert
    assert any("click" in v.detail for v in ps213)


def test_try_except_guard_does_NOT_suppress_ps213(tmp_path):
    # Arrange — wrapping the import in try/except ImportError is NOT a
    # substitute for pinning click in core. The graceful runtime fallback
    # is exactly what PS-213 wants to surface as a CI failure.
    cli_body = (
        "try:\n    import click\nexcept ImportError:\n"
        "    click = None  # graceful fallback\n\n"
        "def main():\n    pass\n"
    )
    _write_pyproject(
        tmp_path,
        dependencies=[],
        optional_dependencies={"cli": ["click>=8.0"]},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(tmp_path, init_body="", cli_body=cli_body)
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert "PS-213" in _codes(out)


# --- lazy-extra-pattern OK (info) --------------------------------------------


def test_lazy_extra_pattern_emits_ps213i_info(tmp_path):
    # Arrange — `newb` in [skills] extra, lazy-imported inside a function
    # body that ALSO raises with a `pip install scitex-fakecli[skills]`
    # install hint. This is the permitted pattern.
    skills_body = (
        "def self_explain():\n"
        "    try:\n        import newb\n    except ImportError as exc:\n"
        '        raise SystemExit(\n'
        '            "Install with: pip install \\"scitex-fakecli[skills]\\""\n'
        "        ) from exc\n"
        "    return newb\n"
    )
    _write_pyproject(
        tmp_path,
        dependencies=["click>=8.0"],
        optional_dependencies={"skills": ["newb>=0.3"]},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body=skills_body,
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert "PS-213i" in _codes(out)


def test_lazy_import_without_install_hint_emits_no_ps213i(tmp_path):
    # Arrange — function-scope import, but no `pip install <pkg>[<x>]`
    # hint string. PS-213i should NOT fire (no auditable signal).
    skills_body = (
        "def self_explain():\n"
        "    import newb\n"
        "    return newb\n"
    )
    _write_pyproject(
        tmp_path,
        dependencies=["click>=8.0"],
        optional_dependencies={"skills": ["newb>=0.3"]},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body=skills_body,
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert "PS-213i" not in _codes(out)


# --- robustness --------------------------------------------------------------


def test_missing_pyproject_emits_nothing(tmp_path):
    # Arrange — no pyproject.toml at all.
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert out == []


def test_no_optional_deps_emits_nothing(tmp_path):
    # Arrange — entry-point exists, click is core, no extras at all.
    _write_pyproject(
        tmp_path,
        dependencies=["click>=8.0"],
        optional_dependencies={},
        scripts={"fakecli": f"{_IMPORT_NAME}._cli:main"},
    )
    _write_pkg(
        tmp_path,
        init_body="",
        cli_body="import click\n\ndef main():\n    pass\n",
    )
    # Act
    out: list = []
    check_ps213_console_script_core_deps(tmp_path, _DIST, _StubViolation, out)
    # Assert
    assert out == []


# EOF
