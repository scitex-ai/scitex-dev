from pathlib import Path

from scitex_dev.ci.runner._storage import assess_storage


def test_assessment_refuses_non_runner_directory(tmp_path: Path):
    # Arrange
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()

    # Act
    result = assess_storage(source, destination)

    # Assert
    check = next(c for c in result.checks if c.name == "runner_identity")
    assert check.to_dict()["ok"] is False


def test_assessment_refuses_same_filesystem(tmp_path: Path):
    # Arrange
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()
    (source / ".runner").write_text("{}")

    # Act
    result = assess_storage(source, destination)

    # Assert
    check = next(c for c in result.checks if c.name == "different_filesystem")
    assert check.to_dict()["ok"] is False


def test_assessment_refuses_nonempty_destination(tmp_path: Path):
    # Arrange
    source = tmp_path / "runner"
    destination = tmp_path / "capacity" / "runner"
    source.mkdir()
    (source / ".runner").write_text("{}")
    destination.mkdir(parents=True)
    (destination / "unexpected").write_text("data")

    # Act
    result = assess_storage(source, destination)

    # Assert
    check = next(c for c in result.checks if c.name == "destination_empty")
    assert check.to_dict()["ok"] is False
