"""Tests for the ecosystem dashboard renderer."""

from __future__ import annotations


def test_render_module_exposes_render_table_and_helpers_callable__render_render_table():
    """`_render` must expose the public renderer surface the dashboard
    CLI relies on. A bare `importlib.import_module` smoke test would
    only catch a syntax error; this test catches accidental rename or
    removal of the actual exported callables."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard import _render

    assert callable(_render.render_table)
    # PackageState is the data class the renderer consumes.


def test_render_module_exposes_render_table_and_helpers_callable__render_cols_for_verbosity():
    """`_render` must expose the public renderer surface the dashboard
    CLI relies on. A bare `importlib.import_module` smoke test would
    only catch a syntax error; this test catches accidental rename or
    removal of the actual exported callables."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard import _render

    assert callable(_render.cols_for_verbosity)
    # PackageState is the data class the renderer consumes.


def test_render_module_exposes_render_table_and_helpers_callable__render_enrichers_for_cols():
    """`_render` must expose the public renderer surface the dashboard
    CLI relies on. A bare `importlib.import_module` smoke test would
    only catch a syntax error; this test catches accidental rename or
    removal of the actual exported callables."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard import _render

    assert callable(_render.enrichers_for_cols)
    # PackageState is the data class the renderer consumes.


def test_render_module_exposes_render_table_and_helpers_isinstance__render_packagestate_type():
    """`_render` must expose the public renderer surface the dashboard
    CLI relies on. A bare `importlib.import_module` smoke test would
    only catch a syntax error; this test catches accidental rename or
    removal of the actual exported callables."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard import _render

    # PackageState is the data class the renderer consumes.
    assert isinstance(_render.PackageState, type)


def test_cols_for_verbosity_returns_more_cols_at_higher_verbosity_len_cols_v2_len_cols_v0():
    """The renderer's column-selection helper is the real contract; this
    locks in the monotonic-grows-with-verbosity behaviour."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._render import cols_for_verbosity

    cols_v0 = cols_for_verbosity(0)
    cols_v2 = cols_for_verbosity(2)
    assert len(cols_v2) >= len(cols_v0)


def test_cols_for_verbosity_returns_more_cols_at_higher_verbosity_set_cols_v0_issubset_set_cols_v2():
    """The renderer's column-selection helper is the real contract; this
    locks in the monotonic-grows-with-verbosity behaviour."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._render import cols_for_verbosity

    cols_v0 = cols_for_verbosity(0)
    cols_v2 = cols_for_verbosity(2)
    assert set(cols_v0).issubset(set(cols_v2))


def test_release_column_shown_at_default_verbosity():
    """The GH-Release column was added 2026-05-27 alongside TAG/PYPI.
    It must appear at the default verbosity tier (=1) so the
    `dashboard list` operator sees it without any extra flag.
    """
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._render import cols_for_verbosity

    # Act
    cols_v1 = cols_for_verbosity(1)
    # Assert
    assert "release" in cols_v1


def test_release_column_is_wired_to_gh_release_enricher():
    """Visible-cols → enrichers mapping must route `release` through
    the `gh-release` enricher (NOT `pypi`, NOT `deep`), so the
    dashboard CLI computes the cell whenever the column is visible."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._render import (
        enrichers_for_cols,
    )

    # Act
    enrichers = enrichers_for_cols(["pkg", "release"])
    # Assert
    assert "gh-release" in enrichers


def test_color_version_cell_release_missing_when_tag_present():
    """The MISSING-release rendering: when `gh_release_lookup_done` is
    True and `tag_latest` is set but `gh_release_latest` is empty,
    the cell must read `MISSING`. This is the canonical 2026-05-27
    footgun signal — PyPI succeeded but the GH Release job's awk
    extractor failed, so no Release got created.
    """
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._render import (
        _color_version_cell,
    )
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    state = PackageState(
        pkg="crossref-local",
        version_pyproject="0.7.4",
        tag_latest="v0.7.4",
        gh_release_latest="",
        gh_release_lookup_done=True,
    )
    # Act
    cell = _color_version_cell(state, "release")
    # Assert
    assert "MISSING" in str(cell)


def test_color_version_cell_release_NC_when_lookup_pending():
    """While the gh-release enricher hasn't run yet,
    `gh_release_lookup_done` is False and the cell must read N/C —
    same convention as the PyPI column's pre-lookup placeholder.
    """
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._render import (
        _color_version_cell,
    )
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    state = PackageState(
        pkg="scitex-foo",
        version_pyproject="0.1.0",
        tag_latest="v0.1.0",
        gh_release_latest="",
        gh_release_lookup_done=False,
    )
    # Act
    cell = _color_version_cell(state, "release")
    # Assert
    assert "N/C" in str(cell)
