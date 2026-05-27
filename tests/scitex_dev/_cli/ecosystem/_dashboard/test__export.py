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


# ---------------------------------------------------------------------------
# to_pdf coverage — drives the pandoc + emacs branches using real shell-
# script fakes on PATH (STX-NM002 forbids monkeypatch). Each fake creates
# a real .pdf file on disk so `to_pdf`'s success branch sees the artefact
# it expects.
# ---------------------------------------------------------------------------


def _install_fake_pandoc(bin_dir: "object", *, exit_code: int = 0) -> None:
    """Drop an executable `pandoc` script that creates the requested
    output file (the `-o <path>` argument) and exits with the given
    status. Mirrors the real pandoc CLI well enough to drive
    `to_pdf`'s pandoc branch."""
    import stat
    from pathlib import Path as _Path

    bin_dir = _Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "pandoc"
    # The fake reads its own argv to find `-o <output>` and writes a
    # minimal PDF magic header so `Path(output).is_file()` is True.
    # `#!/bin/sh` (absolute) survives PATH replacement; the test
    # strips PATH down to a single bin dir, so the kernel-level env
    # lookup for `bash` would fail.
    script.write_text(
        "#!/bin/sh\n"
        'out=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -o) out="$2"; shift 2 ;;\n'
        '    *)  shift ;;\n'
        '  esac\n'
        'done\n'
        'if [ -n "$out" ]; then printf "%%PDF-1.4\\n" > "$out"; fi\n'
        'exit "${FAKE_PANDOC_EXIT-0}"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    import os as _os

    _os.environ["FAKE_PANDOC_EXIT"] = str(exit_code)


def _install_fake_emacs(bin_dir: "object", *, exit_code: int = 0) -> None:
    """Drop an executable `emacs` script that mimics
    `emacs --batch <file>.org -f org-latex-export-to-pdf`: it finds
    the `.org` filename in argv, writes a minimal PDF alongside it
    with the same stem, and exits with the given status."""
    import stat
    from pathlib import Path as _Path

    bin_dir = _Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "emacs"
    script.write_text(
        "#!/bin/sh\n"
        'org=""\n'
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    *.org) org="$a" ;;\n'
        '  esac\n'
        'done\n'
        'if [ -n "$org" ]; then\n'
        '  pdf="${org%.org}.pdf"\n'
        '  printf "%%PDF-1.4\\n" > "$pdf"\n'
        'fi\n'
        'exit "${FAKE_EMACS_EXIT-0}"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    import os as _os

    _os.environ["FAKE_EMACS_EXIT"] = str(exit_code)


def _swap_path(bin_dir: "object") -> str:
    """Replace ``$PATH`` so only ``bin_dir`` is visible. Returns
    the previous PATH so callers can restore it in ``finally``."""
    import os as _os

    saved = _os.environ.get("PATH", "")
    _os.environ["PATH"] = str(bin_dir)
    return saved


def _restore_path(saved: str) -> None:
    import os as _os

    _os.environ["PATH"] = saved
    for k in ("FAKE_PANDOC_EXIT", "FAKE_EMACS_EXIT"):
        _os.environ.pop(k, None)


def test_to_pdf_pandoc_branch_returns_ok_on_success(tmp_path):
    """When `pandoc` is on PATH and exits 0 after writing the PDF,
    `to_pdf` reports status=ok with tool=pandoc."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_pandoc(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["status"] == "ok"


def test_to_pdf_pandoc_branch_reports_pandoc_as_the_tool(tmp_path):
    """The result dict's `tool` field must identify which converter
    actually produced the PDF — used by the CLI to print
    `wrote ... via pandoc`."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_pandoc(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["tool"] == "pandoc"


def test_to_pdf_pandoc_branch_writes_pdf_file(tmp_path):
    """The pandoc success path produces a real file at the requested
    output path (not just a status dict)."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_pandoc(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert target.is_file()


def test_to_pdf_pandoc_failure_returns_error_status(tmp_path):
    """When pandoc exits non-zero (e.g. missing LaTeX engine), the
    result reports status=error so the CLI can surface it without
    losing the .org sidecar."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_pandoc(bin_dir, exit_code=1)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["status"] == "error"


def test_to_pdf_emacs_branch_used_when_pandoc_absent(tmp_path):
    """If only `emacs` is on PATH (no pandoc), `to_pdf` falls back to
    the `emacs --batch ... org-latex-export-to-pdf` pipeline and
    reports tool=emacs on success."""
    # Arrange — install emacs but NOT pandoc.
    bin_dir = tmp_path / "bin"
    _install_fake_emacs(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["tool"] == "emacs"


def test_to_pdf_emacs_branch_returns_ok_on_success(tmp_path):
    """Symmetric to the pandoc-success test — emacs success must
    report status=ok so the CLI prints `wrote ... via emacs`."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_emacs(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["status"] == "ok"


def test_to_pdf_emacs_branch_relocates_pdf_to_requested_path(tmp_path):
    """Emacs writes the PDF next to the .org under the same stem;
    `to_pdf` moves it to the operator's requested output path when
    they differ. The artefact must end up at the requested path."""
    # Arrange — request the PDF in a subdirectory that differs from
    # the org sidecar's natural location only by name; the fake
    # emacs writes alongside the .org so `to_pdf` must rename.
    bin_dir = tmp_path / "bin"
    _install_fake_emacs(bin_dir, exit_code=0)
    saved = _swap_path(bin_dir)
    target = tmp_path / "renamed-output.pdf"
    s = _make_state()
    # Act
    try:
        exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert target.is_file()


def test_to_pdf_emacs_failure_returns_error_status(tmp_path):
    """When emacs exits non-zero (missing LaTeX), the result reports
    status=error and the .org sidecar is still on disk so the
    operator can re-run the convert by hand."""
    # Arrange — emacs that exits 1 AND deletes nothing, so the
    # produced.is_file() check fails too.
    import stat
    from pathlib import Path as _Path

    bin_dir = _Path(tmp_path / "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "emacs"
    script.write_text("#!/bin/sh\nexit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    assert result["status"] == "error"


def test_to_pdf_always_writes_org_sidecar_even_when_pandoc_fails(tmp_path):
    """The .org file is the canonical source — `to_pdf` must always
    write it before attempting the conversion, so a failing
    converter never destroys the operator's report."""
    # Arrange
    bin_dir = tmp_path / "bin"
    _install_fake_pandoc(bin_dir, exit_code=1)
    saved = _swap_path(bin_dir)
    target = tmp_path / "report.pdf"
    s = _make_state()
    # Act
    try:
        result = exp.to_pdf([s], target)
    finally:
        _restore_path(saved)
    # Assert
    from pathlib import Path as _Path

    assert _Path(result["org"]).is_file()
