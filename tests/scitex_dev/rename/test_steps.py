"""Protected-only matches stay visible without broadening rename scope."""

import pytest

from scitex_dev import preview_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.steps import _literal_replace_content


@pytest.fixture(
    params=[
        ('prog_name="scitex-business"\n', "scitex-business"),
        ('StorePlugin(name="business_actuals")\n', "business_actuals"),
        ('db_table = "business_actuals"\n', "business_actuals"),
    ]
)
def protected_preview(tmp_path, request):
    body, pattern = request.param
    target = tmp_path / "cli.py"
    target.write_text(body)
    result = preview_rename(pattern, "replacement", directory=str(tmp_path))
    return result, target, body


@pytest.mark.parametrize(
    "key,expected",
    [
        ("content_files", 0),
        ("content_matches", 0),
        ("content_protected", 1),
        ("protected_files", 1),
    ],
)
def test_protected_only_summary(protected_preview, key, expected):
    # Arrange
    result, _, _ = protected_preview
    # Act
    actual = result.summary[key]
    # Assert
    assert actual == expected


def test_protected_only_preview_detail(protected_preview):
    # Arrange
    result, _, _ = protected_preview
    # Act
    actual = result.contents[0]["lines"][0]["action"]
    # Assert
    assert actual == "protect"


def test_protected_only_preview_preserves_bytes(protected_preview):
    # Arrange
    _, target, body = protected_preview
    # Act
    actual = target.read_text()
    # Assert
    assert actual == body


@pytest.fixture
def protected_application(tmp_path):
    target = tmp_path / "cli.py"
    body = 'prog_name="scitex-business"\n'
    target.write_text(body)
    before = target.stat()
    config = RenameConfig("scitex-business", "scitex-affairs", dry_run=False)
    result = _literal_replace_content(config, target, body, "c-000", False)
    return result, target, body, before


@pytest.mark.parametrize("key,expected", [("protected", 1), ("matches", 0)])
def test_protected_only_apply_report(protected_application, key, expected):
    # Arrange
    result, _, _, _ = protected_application
    # Act
    actual = result[key]
    # Assert
    assert actual == expected


def test_protected_only_apply_preserves_bytes(protected_application):
    # Arrange
    _, target, body, _ = protected_application
    # Act
    actual = target.read_text()
    # Assert
    assert actual == body


@pytest.mark.parametrize("field", ["st_mtime_ns", "st_ino"])
def test_protected_only_apply_does_not_rewrite(protected_application, field):
    # Arrange
    _, target, _, before = protected_application
    # Act
    actual = getattr(target.stat(), field)
    # Assert
    assert actual == getattr(before, field)


@pytest.mark.parametrize(
    "key,expected",
    [
        ("content_files", 1),
        ("content_matches", 1),
        ("content_protected", 1),
    ],
)
def test_plain_quoted_string_is_replaceable(tmp_path, key, expected):
    # Arrange
    (tmp_path / "cli.py").write_text('label = "business"\nprog_name="business"\n')
    # Act
    result = preview_rename("business", "affairs", directory=str(tmp_path))
    # Assert
    assert result.summary[key] == expected


def _collision_tree_state(root):
    import os

    files = [root / name for name in ["alpha.py", "beta.py", "notes.txt", "payload.txt"]]
    return {file.name: ("link", os.readlink(file)) if file.is_symlink() else ("file", file.read_text()) for file in files if file.exists() or file.is_symlink()}


@pytest.fixture(params=[(kind, state) for kind in ["file", "symlink"] for state in ["dangling", "existing", "absent"]])
def _dangling_collision_case(request, tmp_path):
    import subprocess

    kind, state = request.param
    root = tmp_path / "owned-repo"
    root.mkdir()
    source, target = root / "alpha.py", root / "beta.py"
    (root / "payload.txt").write_text("VALUE = 1\n")
    (root / "notes.txt").write_text("alpha\n")
    if kind == "file":
        source.write_text("VALUE = 1\n")
    else:
        source.symlink_to("payload.txt")
    if state == "dangling":
        target.symlink_to("missing.txt")
    elif state == "existing":
        target.write_text("DESTINATION = 2\n")
    for args in [["init"], ["config", "user.name", "Owned rename fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned rename fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = _collision_tree_state(root)
    expected = dict(before)
    if state == "absent":
        expected["beta.py"] = expected.pop("alpha.py")
        expected["notes.txt"] = ("file", "beta\n")
    return root, state, before, expected


def test_dangling_collision_preview_reports_occupied_target(_dangling_collision_case):
    # Arrange
    root, state, _, _ = _dangling_collision_case
    # Act
    result = preview_rename("alpha", "beta", directory=str(root))
    # Assert
    assert result.summary["collisions"] == int(state != "absent")


def test_dangling_collision_preview_preserves_paths_and_bytes(_dangling_collision_case):
    # Arrange
    root, _, before, _ = _dangling_collision_case
    # Act
    preview_rename("alpha", "beta", directory=str(root))
    # Assert
    assert _collision_tree_state(root) == before


@pytest.fixture
def _dangling_collision_application(_dangling_collision_case):
    from scitex_dev import execute_rename

    root, state, before, expected = _dangling_collision_case
    file = root / "notes.txt"
    info = file.stat()
    result = execute_rename("alpha", "beta", directory=str(root))
    after = file.stat()
    return root, state, expected, result, (info.st_ino, info.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)


def test_dangling_collision_apply_refuses_occupied_target(_dangling_collision_application):
    # Arrange
    _, state, _, result, _ = _dangling_collision_application
    # Act
    refused = bool(result.error and "Collisions detected" in result.error)
    # Assert
    assert refused == (state != "absent")


def test_dangling_collision_apply_preserves_or_renames_exact_state(_dangling_collision_application):
    # Arrange
    root, _, expected, _, _ = _dangling_collision_application
    # Act
    actual = _collision_tree_state(root)
    # Assert
    assert actual == expected


def test_dangling_collision_refusal_precedes_content_writes(_dangling_collision_application):
    # Arrange
    _, state, _, _, unchanged = _dangling_collision_application
    # Act
    expected = state != "absent"
    # Assert
    assert unchanged == expected
