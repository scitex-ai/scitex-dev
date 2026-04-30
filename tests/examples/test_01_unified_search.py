"""Smoke test for examples/01_unified_search.py — runs end-to-end and
verifies it produces the expected output file. Fails on import/runtime
errors so example drift breaks CI."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest


_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "01_unified_search.py"


@pytest.mark.skipif(not _EXAMPLE.is_file(), reason="example file moved or removed")
def test_example_runs_and_produces_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Stub the search() result so the example doesn't depend on a populated
    # docs index (the example exercises the API surface, not real data).
    import scitex_dev

    monkeypatch.setattr(scitex_dev, "search", lambda *a, **kw: [])
    runpy.run_path(str(_EXAMPLE), run_name="__main__")
    out = _EXAMPLE.parent / "01_unified_search_out" / "search_results.json"
    assert out.is_file()
    json.loads(out.read_text())  # valid JSON
