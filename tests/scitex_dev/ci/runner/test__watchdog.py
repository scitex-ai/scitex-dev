"""Tests for the pure health-assessment logic of the runner watchdog."""

from scitex_dev.ci.runner._watchdog import assess_health


def test_assess_health_online_runner_and_lease_is_healthy():
    # Arrange
    online_labels = [["self-hosted", "Linux", "X64", "scitex-ci"]]
    lease_running = True
    # Act
    healthy, alerts = assess_health(online_labels, lease_running)
    # Assert
    assert (healthy, alerts) == (True, [])


def test_assess_health_no_matching_runner_is_unhealthy():
    # Arrange
    online_labels = [["self-hosted", "Linux", "X64", "other-label"]]
    lease_running = True
    # Act
    healthy, _alerts = assess_health(online_labels, lease_running)
    # Assert
    assert healthy is False


def test_assess_health_missing_lease_reports_lease_alert():
    # Arrange
    online_labels = [["self-hosted", "scitex-ci"]]
    lease_running = False
    # Act
    _healthy, alerts = assess_health(online_labels, lease_running)
    # Assert
    assert any("lease" in a for a in alerts)


def test_assess_health_never_returns_a_hosted_fallback_action():
    # Arrange — a fully-down state must still yield only alerts, never a flip.
    online_labels = []
    lease_running = False
    # Act
    healthy, alerts = assess_health(online_labels, lease_running)
    # Assert
    assert healthy is False and len(alerts) == 2
