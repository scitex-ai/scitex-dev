"""Tests for open-PR check classification (pure function, no API, no mocks)."""

from scitex_dev._cli.ecosystem._dashboard import _pr_state


def test_classify_failed_checkrun():
    # Arrange
    node = {
        "__typename": "CheckRun",
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "name": "audit",
    }
    # Act
    result = _pr_state._classify(node)
    # Assert
    assert result == ("failed", "audit")


def test_classify_running_checkrun():
    # Arrange
    node = {"__typename": "CheckRun", "status": "IN_PROGRESS", "name": "pytest"}
    # Act
    result = _pr_state._classify(node)
    # Assert
    assert result == ("running", "pytest")


def test_classify_success_checkrun():
    # Arrange
    node = {
        "__typename": "CheckRun",
        "status": "COMPLETED",
        "conclusion": "SUCCESS",
        "name": "docs",
    }
    # Act
    result = _pr_state._classify(node)
    # Assert
    assert result == ("success", "docs")


def test_classify_failed_status_context():
    # Arrange
    node = {"__typename": "StatusContext", "state": "FAILURE", "context": "CLAssistant"}
    # Act
    result = _pr_state._classify(node)
    # Assert
    assert result == ("failed", "CLAssistant")


def test_classify_pending_status_context():
    # Arrange
    node = {"__typename": "StatusContext", "state": "PENDING", "context": "codecov"}
    # Act
    result = _pr_state._classify(node)
    # Assert
    assert result == ("pending", "codecov")
