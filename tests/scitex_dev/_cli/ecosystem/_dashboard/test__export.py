"""Tests for the dashboard export module.

Covers the 2026-05-27 additions:
  - `to_markdown` / `to_org` include the GH-Release (RELEASE) column
    alongside TAG and PYPI.
  - `to_org` emits a "GH-Release gaps" section for packages with a
    local tag but no GH Release (the crossref-local / openalex-local
    footgun where the awk extractor failed the release job).
  - `to_pdf` writes the .org sidecar even when no converter is on
    PATH, returning a structured dict (never raises).
"""

from __future__ import annotations

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


def test_to_markdown_includes_release_header():
    """RELEASE column must appear in the markdown header row so the
    GH-Release-vs-tag gap is visible in pasted README tables."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_markdown([s])
    # Assert
    assert "RELEASE" in out


def test_to_markdown_renders_release_tag_value():
    """When a release exists, its tag string appears verbatim in the
    rendered markdown row."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_markdown([s])
    # Assert
    assert "v0.1.0" in out


def test_to_markdown_shows_MISSING_when_tag_but_no_release():
    """Tag present + lookup done + no release = MISSING signal,
    consistent with the renderer's red MISSING cell."""
    # Arrange
    s = _make_state(gh_release_latest="", gh_release_lookup_done=True)
    # Act
    out = exp.to_markdown([s])
    # Assert
    assert "MISSING" in out


def test_to_markdown_shows_NC_when_release_lookup_not_done():
    """Before the gh-release enricher runs, the cell is N/C — same
    convention as the PyPI column's pre-lookup placeholder."""
    # Arrange
    s = _make_state(gh_release_latest="", gh_release_lookup_done=False)
    # Act
    out = exp.to_markdown([s])
    # Assert
    assert "N/C" in out


def test_to_org_starts_with_title_directive():
    """Org-mode reports start with `#+TITLE:` so pandoc / emacs both
    detect them as Org buffers."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_org([s])
    # Assert
    assert out.startswith("#+TITLE:")


def test_to_org_includes_author_directive():
    """Required for the ywatanabe "usual PDF" convention — the
    author line is part of the standard Org header."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_org([s])
    # Assert
    assert "#+AUTHOR:" in out


def test_to_org_includes_summary_section():
    """The `* Summary` section gives the reader the package count up
    front, before the table."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_org([s])
    # Assert
    assert "* Summary" in out


def test_to_org_emits_release_column():
    """RELEASE column flows from the shared `_report_columns` source
    of truth — the same column appears in markdown and org."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_org([s])
    # Assert
    assert "RELEASE" in out


def test_to_org_emits_gaps_section_when_release_missing():
    """When a package has a tag but no GH Release, the report
    surfaces it under "GH-Release gaps" — the 2026-05-27 footgun
    made visible at the top of the page."""
    # Arrange
    s = _make_state(
        pkg="crossref-local",
        tag_latest="v0.7.4",
        gh_release_latest="",
        gh_release_lookup_done=True,
    )
    # Act
    out = exp.to_org([s])
    # Assert
    assert "GH-Release gaps" in out


def test_to_org_gaps_section_lists_the_missing_package():
    """Each missing package appears by name in the gaps section so
    operators can scan-read the report top-down."""
    # Arrange
    s = _make_state(
        pkg="crossref-local",
        tag_latest="v0.7.4",
        gh_release_latest="",
        gh_release_lookup_done=True,
    )
    # Act
    out = exp.to_org([s])
    # Assert
    assert "crossref-local" in out


def test_to_org_no_gaps_section_when_all_releases_present():
    """If every package has a matching Release, the gaps section is
    omitted (no signal needed, less noise)."""
    # Arrange
    s = _make_state()
    # Act
    out = exp.to_org([s])
    # Assert
    assert "GH-Release gaps" not in out


def test_to_pdf_writes_org_sidecar_when_no_converter(tmp_path):
    """Regardless of whether pandoc/emacs is installed, the .org
    file is always on disk — the operator can finish the conversion
    on a host that has the tool."""
    # Arrange
    s = _make_state()
    target = tmp_path / "report.pdf"
    # Act
    result = exp.to_pdf([s], target)
    # Assert
    assert Path(result["org"]).is_file()


def test_to_pdf_returns_status_org_only_when_converters_absent(tmp_path):
    """With both pandoc and emacs absent (the typical container
    case), `to_pdf` returns status=org_only so the CLI can emit a
    "convert on host" message and exit 0."""
    # Arrange — point PATH at an empty directory so `shutil.which`
    # naturally returns None for every command. Avoids monkeypatch
    # (PA-306 §3 no-mocks bans the fixture).
    import os

    saved_path = os.environ.get("PATH", "")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    os.environ["PATH"] = str(empty_bin)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        os.environ["PATH"] = saved_path
    # Assert
    assert result["status"] == "org_only"


def test_format_release_cell_returns_tag_when_release_present():
    """Release exists → cell renders the tag verbatim."""
    # Arrange
    s = _make_state()
    # Act
    cell = exp._format_release_cell(s)
    # Assert
    assert cell == "v0.1.0"


def test_format_release_cell_returns_MISSING_when_tag_but_no_release():
    """Lookup done, no release, local tag present → MISSING signal."""
    # Arrange
    s = _make_state(gh_release_latest="", gh_release_lookup_done=True)
    # Act
    cell = exp._format_release_cell(s)
    # Assert
    assert cell == "MISSING"


def test_format_release_cell_returns_dash_when_no_tag_and_no_release():
    """Lookup done, no release, no tag → "-" (no signal needed)."""
    # Arrange
    s = _make_state(
        gh_release_latest="",
        gh_release_lookup_done=True,
        tag_latest="",
    )
    # Act
    cell = exp._format_release_cell(s)
    # Assert
    assert cell == "-"


def test_format_release_cell_returns_NC_when_lookup_pending():
    """Lookup not done yet → N/C placeholder."""
    # Arrange
    s = _make_state(gh_release_latest="", gh_release_lookup_done=False)
    # Act
    cell = exp._format_release_cell(s)
    # Assert
    assert cell == "N/C"


def test_to_json_round_trips_gh_release_lookup_done():
    """The new dataclass field must round-trip through to_json so the
    `dashboard list --json` consumer (e.g. the `--host` renderer)
    restores it via PackageState.from_dict."""
    # Arrange
    import json

    s = _make_state()
    # Act
    payload = json.loads(exp.to_json([s]))
    # Assert
    assert payload[0]["gh_release_lookup_done"] is True
