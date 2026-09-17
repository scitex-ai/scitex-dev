"""Freshness policy additions to the developer configuration."""

from scitex_dev._core.config import DevConfig, load_config


def test_dev_config_defaults_to_three_freshness_days():
    # Arrange
    config = DevConfig()
    # Act
    days = config.freshness.freshness_days
    # Assert
    assert days == 3


def test_dev_config_defaults_to_scitex_ai_organization():
    # Arrange
    config = DevConfig()
    # Act
    organization = config.freshness.organization
    # Assert
    assert organization == "scitex-ai"


def test_load_config_accepts_freshness_override(tmp_path):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text(
        "freshness:\n"
        "  organization: other-org\n"
        "  freshness_days: 7\n"
        "  cards: required\n"
    )
    # Act
    loaded = load_config(config)
    actual = (
        loaded.freshness.organization,
        loaded.freshness.freshness_days,
        loaded.freshness.cards,
    )
    # Assert
    assert actual == ("other-org", 7, "required")
