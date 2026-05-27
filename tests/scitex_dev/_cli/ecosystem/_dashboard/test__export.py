"""Tests for the dashboard export module.

Covers the 2026-05-27 additions:
  - `to_markdown` / `to_org` now include the GH-Release (RELEASE)
    column alongside TAG and PYPI.
  - `to_org` emits a "GH-Release gaps" section for packages with a
    local tag but no GH Release (the crossref-local / openalex-local
    footgun where the awk extractor failed the release job).
  - `to_pdf` writes the .org sidecar even when no converter is on
    PATH, returning a structured dict (never raises).
"""

from __future__ import annotations

import json
from pathlib import Path

from scitex_dev._cli.ecosystem._dashboard import _export as exp
from scitex_dev._cli.ecosystem._dashboard._state import PackageState


def _make_state(
    pkg: str = "scitex-foo",
    *,
    version_pyproject: str = "0.1.0",
    tag_latest: str = "v0.1.0",
    pypi_latest: str = "0.1.0",
    gh_release_latest: str = "v0.1.0",
    gh_release_lookup_done: bool = True,
) -> PackageState:
    return PackageState(
        pkg=pkg,
        version_pyproject=version_pyproject,
        tag_latest=tag_latest,
        pypi_latest=pypi_latest,
        gh_release_latest=gh_release_latest,
        gh_release_lookup_done=gh_release_lookup_done,
        exists_locally=True,
    )


def test_to_markdown_includes_release_column():
    s = _make_state()
    out = exp.to_markdown([s])
    assert "RELEASE" in out
    assert "v0.1.0" in out


def test_to_markdown_shows_MISSING_when_tag_but_no_release():
    s = _make_state(gh_release_latest="", gh_release_lookup_done=True)
    out = exp.to_markdown([s])
    assert "MISSING" in out


def test_to_markdown_shows_NC_when_release_lookup_not_done():
    s = _make_state(gh_release_latest="", gh_release_lookup_done=False)
    out = exp.to_markdown([s])
    assert "N/C" in out


def test_to_org_emits_org_header_and_table():
    s = _make_state()
    out = exp.to_org([s])
    assert out.startswith("#+TITLE:")
    assert "#+AUTHOR:" in out
    assert "#+DATE:" in out
    assert "* Summary" in out
    # Org table marker (col 0 starts with `|`)
    assert "\n| PKG " in out
    assert "RELEASE" in out


def test_to_org_emits_gaps_section_for_missing_releases():
    s_ok = _make_state(pkg="scitex-ok")
    s_missing = _make_state(
        pkg="crossref-local",
        tag_latest="v0.7.4",
        gh_release_latest="",
        gh_release_lookup_done=True,
    )
    out = exp.to_org([s_ok, s_missing])
    assert "GH-Release gaps" in out
    assert "crossref-local" in out
    assert "v0.7.4" in out


def test_to_org_no_gaps_section_when_all_releases_present():
    s = _make_state()
    out = exp.to_org([s])
    assert "GH-Release gaps" not in out


def test_to_pdf_always_writes_org_sidecar(tmp_path):
    s = _make_state()
    target = tmp_path / "report.pdf"
    result = exp.to_pdf([s], target)
    # Regardless of pandoc/emacs availability, the .org sidecar is on disk.
    assert Path(result["org"]).is_file()
    assert result["status"] in {"ok", "org_only", "error"}


def test_to_pdf_returns_org_only_when_no_converter_available(
    tmp_path, monkeypatch
):
    """If neither pandoc nor emacs is on PATH, return status=org_only.

    Simulated by monkey-patching ``shutil.which`` to None.
    """
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda _name: None)

    s = _make_state()
    target = tmp_path / "report.pdf"
    result = exp.to_pdf([s], target)
    assert result["status"] == "org_only"
    assert result["pdf"] is None
    assert Path(result["org"]).is_file()
    assert "pandoc" in result["reason"] or "emacs" in result["reason"]


def test_format_release_cell_handles_all_three_states():
    # 1. Release present → return the tag verbatim.
    s = _make_state()
    assert exp._format_release_cell(s) == "v0.1.0"
    # 2. Lookup done, release missing, tag present → MISSING.
    s = _make_state(gh_release_latest="", gh_release_lookup_done=True)
    assert exp._format_release_cell(s) == "MISSING"
    # 3. Lookup done, release missing, NO tag → "-" (no signal needed).
    s = _make_state(
        gh_release_latest="",
        gh_release_lookup_done=True,
        tag_latest="",
    )
    assert exp._format_release_cell(s) == "-"
    # 4. Lookup not done yet → N/C placeholder.
    s = _make_state(gh_release_latest="", gh_release_lookup_done=False)
    assert exp._format_release_cell(s) == "N/C"


def test_to_json_unchanged_includes_gh_release_lookup_done():
    """The new dataclass field must round-trip through to_json so the
    `dashboard list --json` consumer (e.g. the `--host` renderer) can
    restore it via PackageState.from_dict."""
    s = _make_state()
    payload = json.loads(exp.to_json([s]))
    assert payload[0]["gh_release_lookup_done"] is True
