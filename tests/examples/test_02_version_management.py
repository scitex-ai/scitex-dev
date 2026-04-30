"""Smoke test for examples/02_version_management.py."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest


_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "02_version_management.py"


@pytest.mark.skipif(not _EXAMPLE.is_file(), reason="example file moved or removed")
def test_example_runs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import scitex_dev

    monkeypatch.setattr(scitex_dev, "list_versions", lambda *a, **kw: {})
    monkeypatch.setattr(scitex_dev, "get_mismatches", lambda *a, **kw: [])
    runpy.run_path(str(_EXAMPLE), run_name="__main__")
    assert (_EXAMPLE.parent / "02_version_management_out").is_dir()
