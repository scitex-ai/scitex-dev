"""Smoke test for examples/02_version_management.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "02_version_management.py"


@pytest.mark.skipif(not _EXAMPLE.is_file(), reason="example file moved or removed")
def test_example_imports_and_defines_main():
    spec = importlib.util.spec_from_file_location("ex02", _EXAMPLE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        pytest.skip(f"scitex umbrella not importable in this env: {e}")
    assert hasattr(mod, "main")
