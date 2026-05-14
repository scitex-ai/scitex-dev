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
