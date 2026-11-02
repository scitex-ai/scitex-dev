"""Real imported typing aliases must not inflate Python/MCP operation counts."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager

import pytest

from scitex_dev._cli.audit._summary._mcp_parity import (
    _parity_violations,
    _python_api_names,
)

_SURFACE = """from typing import Callable as _Callable, Literal as _Literal

BundleResolver = _Callable[[str], str]
MountResolver = _Callable[..., str]
PaperStage = _Literal['draft', 'published']
Rows = list[str]
Lookup = dict[str, int]

class _Operation:
    def __call__(self):
        return 'called'

run_operation = _Operation()

def read_paper():
    return 'paper'
"""
_PUBLIC = [
    "BundleResolver",
    "MountResolver",
    "PaperStage",
    "Rows",
    "Lookup",
    "run_operation",
    "read_paper",
]


@contextmanager
def _importable_surface(tmp_path, *, nested=False, explicit_all=True):
    """Use real on-disk modules; restore import state without mocking imports."""
    name = "scitex_paritytypedfixture"
    package = tmp_path / name
    package.mkdir()
    surface = _SURFACE + (f"\n__all__ = {_PUBLIC!r}\n" if explicit_all else "")
    if nested:
        (package / "papers.py").write_text(surface)
        (package / "__init__.py").write_text(
            "from . import papers\n__all__ = ['papers']\n"
        )
    else:
        (package / "__init__.py").write_text(surface)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield "scitex-paritytypedfixture"
    finally:
        sys.path.remove(str(tmp_path))
        for loaded in tuple(sys.modules):
            if loaded == name or loaded.startswith(name + "."):
                del sys.modules[loaded]
        importlib.invalidate_caches()


@pytest.mark.parametrize("explicit_all", [True, False])
def test_flat_exports_exclude_typing_aliases_but_keep_real_callables(
    tmp_path, explicit_all
):
    # Arrange
    with _importable_surface(tmp_path, explicit_all=explicit_all) as package:
        # Act
        names = _python_api_names(package)
    # Assert
    assert names == {"read_paper", "run_operation"}


def test_nested_exports_exclude_typing_aliases_but_keep_real_callables(tmp_path):
    # Arrange
    with _importable_surface(tmp_path, nested=True) as package:
        # Act
        names = _python_api_names(package)
    # Assert
    assert names == {"papers_read_paper", "papers_run_operation"}


@pytest.mark.parametrize("nested", [False, True])
def test_real_tools_satisfy_parity_without_fake_tools_for_typing_aliases(
    tmp_path, nested
):
    # Arrange
    prefix = "papers_" if nested else ""
    tools = {prefix + "read_paper", prefix + "run_operation"}
    with _importable_surface(tmp_path, nested=nested) as package:
        # Act
        violations = _parity_violations(package, _python_api_names(package), tools)
    # Assert
    assert violations == []


@pytest.mark.parametrize("nested", [False, True])
def test_missing_real_operations_still_fail_parity(tmp_path, nested):
    # Arrange
    with _importable_surface(tmp_path, nested=nested) as package:
        # Act
        violations = _parity_violations(package, _python_api_names(package), set())
    # Assert
    assert any(
        "2/2 Python APIs have no matching MCP tool" in v.message for v in violations
    )
