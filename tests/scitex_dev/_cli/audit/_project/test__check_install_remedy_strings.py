# -*- coding: utf-8 -*-
"""Tests for `_check_install_remedy_strings.py` (PS-215).

A `pip install <pkg>[<extra>]` string that self-references THIS package
must name an extra that actually exists AND is non-empty in this same
package's pyproject.toml. Each test builds a REAL temp package
directory (no mocks) — a pyproject.toml plus a source or doc file
containing the remedy string — then asserts whether PS-215 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_install_remedy_strings import (
    check_ps215_broken_install_remedy,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_pyproject(repo: Path, extras_block: str, *, name: str = "scitex-writer") -> None:
    repo.joinpath("pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        f"{extras_block}\n",
        encoding="utf-8",
    )


def _write_src(repo: Path, body: str, *, import_name: str = "scitex_writer") -> None:
    pkg_dir = repo / "src" / import_name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "_server.py").write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- PS-215 fires (positive cases) ------------------------------------------


def test_ps215_fires_when_remedy_names_empty_extra(tmp_path):
    # Arrange — the scitex-writer incident shape: editor = [] but the
    # server module recommends `pip install scitex-writer[editor]`.
    _write_pyproject(tmp_path, "editor = []\n")
    _write_src(
        tmp_path,
        'raise RuntimeError("Install with: pip install scitex-writer[editor]")\n',
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert "PS-215" in _codes(out)


def test_ps215_fires_when_remedy_names_nonexistent_extra(tmp_path):
    # Arrange — extras table exists but never declares "editor" at all
    _write_pyproject(tmp_path, 'full = ["scitex-app>=0.1.0"]\n')
    _write_src(
        tmp_path,
        'print("pip install scitex-writer[editor]")\n',
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert "PS-215" in _codes(out)


def test_ps215_fires_on_uv_pip_install_form(tmp_path):
    # Arrange — the `uv pip install` phrasing must also be caught
    _write_pyproject(tmp_path, "editor = []\n")
    _write_src(
        tmp_path,
        '# Recovery hint: uv pip install "scitex-writer[editor]"\n',
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert "PS-215" in _codes(out)


def test_ps215_fires_on_markdown_docs(tmp_path):
    # Arrange — README.md carries the same dead remedy
    _write_pyproject(tmp_path, "editor = []\n")
    tmp_path.joinpath("README.md").write_text(
        "Install with: `pip install scitex-writer[editor]`\n", encoding="utf-8"
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert "PS-215" in _codes(out)


def test_ps215_detail_names_the_offending_extra(tmp_path):
    # Arrange
    _write_pyproject(tmp_path, "editor = []\n")
    _write_src(tmp_path, 'x = "pip install scitex-writer[editor]"\n')
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert "editor" in out[0].detail


# --- PS-215 silent (negative cases) -----------------------------------------


def test_ps215_silent_when_remedy_names_real_nonempty_extra(tmp_path):
    # Arrange — the fixed shape: editor now has a real dependency
    _write_pyproject(tmp_path, 'editor = ["scitex-app>=0.1.0"]\n')
    _write_src(
        tmp_path,
        'raise RuntimeError("Install with: pip install scitex-writer[editor]")\n',
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps215_silent_for_remedy_naming_a_different_package(tmp_path):
    # Arrange — remedy references a PEER package's extra, not this one;
    # verifying a peer's pyproject is out of scope for this cheap check.
    _write_pyproject(tmp_path, "editor = []\n")
    _write_src(
        tmp_path,
        'print("pip install some-other-package[editor]")\n',
    )
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps215_silent_when_no_remedy_string_present(tmp_path):
    # Arrange — empty extra exists but nothing in source references it
    _write_pyproject(tmp_path, "editor = []\n")
    _write_src(tmp_path, "def f():\n    return 1\n")
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert out == []


def test_ps215_silent_when_pyproject_absent(tmp_path):
    # Arrange — empty repo, no pyproject.toml
    out: list = []
    # Act
    check_ps215_broken_install_remedy(tmp_path, "scitex-writer", _StubViolation, out)
    # Assert
    assert out == []


# EOF
