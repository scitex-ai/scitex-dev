"""Standard headers are reusable; custom distribution versions stay authoritative."""

from importlib.metadata import PathDistribution

from scitex_dev.cli_providers._metadata_snapshot import _MetadataSnapshot


def test_custom_distribution_version_override_is_preserved(tmp_path):
    # Arrange
    info = tmp_path / "owned-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: owned\nVersion: 1.0\n")

    class CustomDistribution(PathDistribution):
        @property
        def version(self):
            return "custom-version"

    distribution = CustomDistribution(info)
    snapshot = _MetadataSnapshot()

    # Act
    observed = (
        snapshot.headers(distribution)["Version"],
        snapshot.version(distribution),
    )

    # Assert
    assert observed == ("1.0", "custom-version")
