"""Real filesystem controls for projection commit and concurrent-change detection."""

from scitex_dev._ecosystem._skills.transaction import (
    _locked_store,
    _promote_projection,
    _snapshot,
)


def test_real_filesystem_promotion_failure_restores_original(tmp_path):
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    original = target / "original.txt"
    original.write_text("keep original")
    missing_stage = tmp_path / "missing-stage"
    backup = tmp_path / "backup"
    # Act
    try:
        _promote_projection(missing_stage, target, backup)
        failure = None
    except FileNotFoundError as error:
        failure = type(error).__name__
    # Assert
    assert (failure, original.read_text(), backup.exists()) == (
        "FileNotFoundError",
        "keep original",
        False,
    )


def test_snapshot_observes_changed_content_behind_namespace_symlink(tmp_path):
    # Arrange
    source = tmp_path / "source"
    source.mkdir()
    document = source / "SKILL.md"
    document.write_text("before")
    target = tmp_path / "store"
    target.mkdir()
    (target / "example").symlink_to(source, target_is_directory=True)
    before = _snapshot(target)
    # Act
    document.write_text("after")
    after = _snapshot(target)
    # Assert
    assert after != before


def test_lock_symlink_refuses_without_touching_foreign_file(tmp_path):
    # Arrange
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("foreign content")
    before_mode = foreign.stat().st_mode
    target = tmp_path / "skills"
    (tmp_path / ".skills.skills-install.lock").symlink_to(foreign)
    entered = False
    # Act
    try:
        with _locked_store(target):
            entered = True
    except (OSError, ValueError):
        pass
    # Assert
    assert (entered, foreign.read_text(), foreign.stat().st_mode) == (
        False,
        "foreign content",
        before_mode,
    )
