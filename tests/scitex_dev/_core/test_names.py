"""Distribution identities remain canonical and cannot become URL/path inputs."""

import pytest

from scitex_dev import normalize_distribution_name


@pytest.mark.parametrize("name,expected", [
    ("SciTeX_Scholar", "scitex-scholar"), ("scitex..SDK", "scitex-sdk"), ("x", "x"),
])
def test_distribution_identity_normalizes(name, expected):
    # Arrange
    candidate = name
    # Act
    actual = normalize_distribution_name(candidate)
    # Assert
    assert actual == expected


@pytest.mark.parametrize("name", [
    "../scitex", "/home/agent", "https://example.test", "scitex>=1", "scitex[all]",
    "scitex\n", "scitex\r\n", " scitex", "scitex\x00", "scitéx", "", None,
])
def test_invalid_distribution_identity_is_refused(name):
    # Arrange
    candidate = name
    # Act
    refused = False
    try:
        normalize_distribution_name(candidate)
    except ValueError:
        refused = True
    # Assert
    assert refused
