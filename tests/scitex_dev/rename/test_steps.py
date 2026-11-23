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


def _directory_collision_state(base):
    import os

    state = {}
    for file in base.rglob("*"):
        if ".git" in file.parts:
            continue
        name = str(file.relative_to(base))
        state[name] = ("link", os.readlink(file)) if file.is_symlink() else ("directory", "") if file.is_dir() else ("file", file.read_text())
    return state


@pytest.fixture(params=["dangling", "link-file", "link-directory", "file", "directory", "absent"])
def _directory_target_case(request, tmp_path):
    import subprocess

    state = request.param
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("KEEP = 1\n")
    (root / "notes.txt").write_text("alpha_pkg\n")
    source, target = root / "alpha_pkg", root / "beta_pkg"
    source.mkdir()
    (source / "module.txt").write_text("VALUE = 1\n")
    if state == "dangling":
        target.symlink_to("../missing")
    elif state == "link-file":
        target.symlink_to("../outside/keep.txt")
    elif state == "link-directory":
        target.symlink_to("../outside")
    elif state == "file":
        target.write_text("DESTINATION = 2\n")
    elif state == "directory":
        target.mkdir()
        (target / "keep.txt").write_text("DESTINATION = 2\n")
    for args in [["init"], ["config", "user.name", "Owned directory fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned directory fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = _directory_collision_state(tmp_path)
    expected = dict(before)
    if state in ["directory", "absent"]:
        expected["repo/beta_pkg"] = expected.pop("repo/alpha_pkg")
        expected["repo/beta_pkg/module.txt"] = expected.pop("repo/alpha_pkg/module.txt")
        expected["repo/notes.txt"] = ("file", "beta_pkg\n")
    return root, state, before, expected


def test_directory_target_preview_counts_occupied_destination(_directory_target_case):
    # Arrange
    root, state, _, _ = _directory_target_case
    # Act
    result = preview_rename("alpha_pkg", "beta_pkg", directory=str(root))
    # Assert
    assert result.summary["collisions"] == int(state != "absent")


def test_directory_target_preview_marks_only_real_directory_merge(_directory_target_case):
    # Arrange
    root, state, _, _ = _directory_target_case
    # Act
    result = preview_rename("alpha_pkg", "beta_pkg", directory=str(root))
    # Assert
    assert result.dir_names[0]["merged"] == (state == "directory")


@pytest.fixture
def _directory_target_application(_directory_target_case):
    from scitex_dev import execute_rename

    root, state, before, expected = _directory_target_case
    info = (root / "notes.txt").stat()
    try:
        result = execute_rename("alpha_pkg", "beta_pkg", directory=str(root))
    except OSError:
        result = None
    after = (root / "notes.txt").stat()
    return root, state, expected, result, (info.st_ino, info.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)


def test_directory_target_apply_refuses_non_directory_destination(_directory_target_application):
    # Arrange
    _, state, _, result, _ = _directory_target_application
    # Act
    refused = bool(result and result.error and "Collisions detected" in result.error)
    # Assert
    assert refused == (state not in ["directory", "absent"])


def test_directory_target_apply_preserves_or_moves_exact_owned_state(_directory_target_application):
    # Arrange
    root, _, expected, _, _ = _directory_target_application
    # Act
    actual = _directory_collision_state(root.parent)
    # Assert
    assert actual == expected


def test_directory_target_refusal_precedes_all_content_writes(_directory_target_application):
    # Arrange
    _, state, _, _, unchanged = _directory_target_application
    # Act
    expected = state not in ["directory", "absent"]
    # Assert
    assert unchanged == expected


@pytest.fixture(params=[(regex, state) for regex in [False, True] for state in ["dangling", "link-file", "link-directory", "file", "directory", "absent"]])
def _relative_target_case(request, tmp_path):
    import subprocess

    regex, state = request.param
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("KEEP = 1\n")
    (root / "notes.txt").write_text("alpha/pkg\n")
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    source, target = root / "alpha/pkg", root / "beta/pkg"
    source.mkdir()
    (source / "module.txt").write_text("VALUE = 1\n")
    if state == "dangling":
        target.symlink_to("../../missing")
    elif state == "link-file":
        target.symlink_to("../../outside/keep.txt")
    elif state == "link-directory":
        target.symlink_to("../../outside")
    elif state == "file":
        target.write_text("DESTINATION = 2\n")
    elif state == "directory":
        target.mkdir()
        (target / "keep.txt").write_text("DESTINATION = 2\n")
    for args in [["init"], ["config", "user.name", "Owned relative fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned relative fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = _directory_collision_state(tmp_path)
    expected = dict(before)
    blocked = state not in ["directory", "absent"]
    if not blocked:
        expected["repo/beta/pkg"] = expected.pop("repo/alpha/pkg")
        expected["repo/beta/pkg/module.txt"] = expected.pop("repo/alpha/pkg/module.txt")
        expected["repo/notes.txt"] = ("file", "beta/pkg\n")
    pattern, replacement = (r"alpha/(pkg)", r"beta/\1") if regex else ("alpha/pkg", "beta/pkg")
    return root, regex, pattern, replacement, blocked, expected


def test_relative_directory_target_checks_preflight_before_writes(_relative_target_case):
    # Arrange
    from scitex_dev import execute_rename

    root, regex, pattern, replacement, blocked, expected = _relative_target_case
    info = (root / "notes.txt").stat()
    # Act
    try:
        result = execute_rename(pattern, replacement, directory=str(root), regex=regex)
    except OSError:
        result = None
    after = (root / "notes.txt").stat()
    refused = bool(result and result.error and "Collisions detected" in result.error)
    preserved = (info.st_ino, info.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)
    # Assert
    assert (refused, _directory_collision_state(root.parent) == expected, preserved) == (blocked, True, blocked)


@pytest.fixture(params=[
    (r"(?<=prefix:)alpha", "beta", "prefix:alpha suffix\n", "alpha", "beta", "prefix:beta suffix\n"),
    (r"alpha(?= suffix)", "beta", "prefix:alpha suffix\n", "alpha", "beta", "prefix:beta suffix\n"),
    (r"(?P<word>alpha)(?= suffix)", r"\g<word>-beta", "prefix:alpha suffix\n", "alpha", "alpha-beta", "prefix:alpha-beta suffix\n"),
    (r"(?<=prefix:)(a)(lpha)", r"\2-\1", "prefix:alpha suffix\n", "alpha", "lpha-a", "prefix:lpha-a suffix\n"),
    (r"(?=alpha)", "MARK", "prefix:alpha suffix\n", "", "MARK", "prefix:MARKalpha suffix\n"),
    (r"(alpha)", r"\1-beta", "prefix:alpha suffix\n", "alpha", "alpha-beta", "prefix:alpha-beta suffix\n"),
    (r"^(alpha)", "beta", "alpha suffix\n", "alpha", "beta", "beta suffix\n"),
    (r"(?<=prefix:)alpha", r"\n", "prefix:alpha suffix\n", "alpha", "\n", "prefix:\n suffix\n"),
])
def _regex_preview_context_case(request, tmp_path):
    import subprocess

    pattern, replacement, body, before, after, expected = request.param
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_text(body)
    for args in [["init"], ["config", "user.name", "Owned regex fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned regex fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    info = file.stat()
    return root, file, pattern, replacement, body, before, after, expected, (file.read_bytes(), info.st_ino, info.st_mtime_ns)


def test_regex_context_preview_uses_original_match(_regex_preview_context_case):
    # Arrange
    root, _, pattern, replacement, _, before, after, _, _ = _regex_preview_context_case
    # Act
    result = preview_rename(pattern, replacement, directory=str(root), regex=True)
    entry = result.contents[0]
    # Assert
    assert (entry["matches"], entry["lines"][0]["before"], entry["lines"][0]["after"]) == (1, before, after)


def test_regex_context_preview_never_rewrites_file(_regex_preview_context_case):
    # Arrange
    root, file, pattern, replacement, _, _, _, _, before = _regex_preview_context_case
    # Act
    preview_rename(pattern, replacement, directory=str(root), regex=True)
    info = file.stat()
    # Assert
    assert (file.read_bytes(), info.st_ino, info.st_mtime_ns) == before


def test_regex_context_apply_keeps_whole_file_semantics(_regex_preview_context_case):
    # Arrange
    from scitex_dev import execute_rename

    root, file, pattern, replacement, _, _, _, expected, _ = _regex_preview_context_case
    # Act
    result = execute_rename(pattern, replacement, directory=str(root), regex=True)
    # Assert
    assert (result.error, file.read_text()) == (None, expected)
