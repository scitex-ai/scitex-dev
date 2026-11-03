"""Existing CLI import paths preserve the shared projection helper identity."""

from scitex_dev._cli.skills._manage import _projection_finalize as cli
from scitex_dev._ecosystem._skills import projection_install as domain


def test_cli_projection_finalizer_keeps_compatibility_identity():
    # Arrange
    expected = domain.finalize_projection
    # Act
    actual = cli.finalize_projection
    # Assert
    assert actual is expected
