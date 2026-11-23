"""Real ripgrep pattern binding preserves option-shaped search strings."""

import shutil
import subprocess

import pytest

from scitex_dev import execute_rename, preview_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _RG_PATH, _rg_find_content_matches

pytestmark = pytest.mark.skipif(shutil.which("rg") is None, reason="Optional ripgrep backend is not installed")


@pytest.fixture(params=[(regex, pattern) for regex in [False, True] for pattern in ["--version", "--help", "needle"]])
def rg_option_case(request, tmp_path):
    regex, pattern = request.param
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_text(pattern + "\n")
    (root / "other.txt").write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned rg fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned rg fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    info = file.stat()
    return root, file, regex, pattern, (file.read_bytes(), info.st_ino, info.st_mtime_ns)


def test_rg_option_backend_finds_exact_real_file(rg_option_case):
    # Arrange
    root, file, regex, pattern, _ = rg_option_case
    config = RenameConfig(pattern, "REPLACED", regex=regex)
    # Act
    files = _rg_find_content_matches(str(root), config)
    # Assert
    assert files == [file]


def test_rg_option_public_preview_counts_content_match(rg_option_case):
    # Arrange
    root, _, regex, pattern, _ = rg_option_case
    # Act
    result = preview_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    # Assert
    assert result.summary["content_matches"] == 1


def test_rg_option_preview_preserves_file_metadata(rg_option_case):
    # Arrange
    root, file, regex, pattern, before = rg_option_case
    # Act
    preview_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    info = file.stat()
    # Assert
    assert (file.read_bytes(), info.st_ino, info.st_mtime_ns) == before


def test_rg_option_actual_apply_replaces_only_expected_content(rg_option_case):
    # Arrange
    root, file, regex, pattern, _ = rg_option_case
    # Act
    result = execute_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    # Assert
    assert (result.error, file.read_text(), (root / "other.txt").read_text()) == (None, "REPLACED\n", "unrelated\n")


@pytest.fixture(params=["ordinary.txt", "line\nbreak.txt", "carriage\rreturn.txt", "tab\tbreak.txt", "unicode\u2028break.txt", "sibling-spoof"])
def rg_filename_case(request, tmp_path):
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("needle external sentinel\n")
    name = request.param
    if name == "sibling-spoof":
        name = "prefix\n" + str(outside)
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("needle\n")
    for args in [["init"], ["config", "user.name", "Owned filename fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned filename fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, outside)]
    return root, file, outside, before


def test_rg_filename_backend_selects_exact_path(rg_filename_case):
    # Arrange
    root, file, _, _ = rg_filename_case
    config = RenameConfig("needle", "REPLACED")
    # Act
    files = _rg_find_content_matches(str(root), config)
    # Assert
    assert files == [file]


def test_rg_filename_public_preview_selects_exact_path(rg_filename_case):
    # Arrange
    root, file, _, _ = rg_filename_case
    # Act
    result = preview_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.summary["content_matches"], [entry["file"] for entry in result.contents]) == (1, [str(file)])


def test_rg_filename_preview_preserves_both_files(rg_filename_case):
    # Arrange
    root, file, outside, before = rg_filename_case
    # Act
    preview_rename("needle", "REPLACED", directory=str(root))
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, outside)]
    # Assert
    assert after == before


def test_rg_filename_application_preserves_sibling(rg_filename_case):
    # Arrange
    root, file, outside, _ = rg_filename_case
    # Act
    result = execute_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.error, file.read_text(), outside.read_text()) == (None, "REPLACED\n", "needle external sentinel\n")


@pytest.fixture(params=[b"ordinary.txt", b"invalid-\xff.txt", b"invalid-\xfe.txt", b"invalid-\xff\nline.txt"])
def rg_byte_name_case(request, tmp_path):
    import os

    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / os.fsdecode(request.param)
    file.write_text("needle\n")
    sibling = root / "other.txt"
    sibling.write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned byte filename fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned byte filename fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    return root, file, sibling, before


def test_rg_byte_name_backend_exact_path(rg_byte_name_case):
    # Arrange
    root, file, _, _ = rg_byte_name_case
    config = RenameConfig("needle", "REPLACED")
    # Act
    result = _rg_find_content_matches(str(root), config)
    # Assert
    assert result == [file]


def test_rg_byte_name_preview_exact_path(rg_byte_name_case):
    # Arrange
    root, file, _, _ = rg_byte_name_case
    # Act
    result = preview_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.summary["content_matches"], [entry["file"] for entry in result.contents]) == (1, [str(file)])


def test_rg_byte_name_preview_preserves_metadata(rg_byte_name_case):
    # Arrange
    root, file, sibling, before = rg_byte_name_case
    # Act
    preview_rename("needle", "REPLACED", directory=str(root))
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    # Assert
    assert after == before


def test_rg_byte_name_apply_preserves_sibling(rg_byte_name_case):
    # Arrange
    root, file, sibling, _ = rg_byte_name_case
    # Act
    result = execute_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.error, file.read_bytes(), sibling.read_bytes()) == (None, b"REPLACED\n", b"unrelated\n")


def test_rg_byte_name_cli_preview_exact_json_path(rg_byte_name_case):
    # Arrange
    import json
    from click.testing import CliRunner
    from scitex_dev._cli._root import main

    root, file, _, _ = rg_byte_name_case
    # Act
    result = CliRunner().invoke(main, ["rename-symbols", "--root", str(root), "--dry-run", "--json", "needle", "REPLACED"])
    payload = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, payload["success"] is True, [entry["file"] for entry in payload["data"]["contents"]]) == (0, True, [str(file)])


def test_rg_byte_name_cli_apply_preserves_sibling(rg_byte_name_case):
    # Arrange
    import json
    from click.testing import CliRunner
    from scitex_dev._cli._root import main

    root, file, sibling, _ = rg_byte_name_case
    # Act
    result = CliRunner().invoke(main, ["rename-symbols", "--root", str(root), "--yes", "--json", "needle", "REPLACED"])
    payload = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, payload["success"] is True, [entry["file"] for entry in payload["data"]["contents"]], file.read_bytes(), sibling.read_bytes()) == (0, True, [str(file)], b"REPLACED\n", b"unrelated\n")


def _run_owned_rg_config(operation, root, config_file, regex):
    import json
    import os
    import sys

    code = """
import dataclasses,json,sys
from scitex_dev import preview_rename,execute_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _rg_find_content_matches
operation,root,regex=sys.argv[1:];regex=regex=='True'
if operation=='backend':
    files=_rg_find_content_matches(root,RenameConfig('needle','REPLACED',regex=regex))
    data=None if files is None else list(map(str,files))
else:
    fn=preview_rename if operation=='preview' else execute_rename
    data=dataclasses.asdict(fn('needle','REPLACED',directory=root,regex=regex))
print(json.dumps(data))
"""
    result = subprocess.run([sys.executable, "-c", code, operation, str(root), str(regex)], env={**os.environ, "RIPGREP_CONFIG_PATH": str(config_file)}, check=True, capture_output=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture(params=[(regex, options) for regex in [False, True] for options in ["", "--quiet\n", "--glob=!*.txt\n"]])
def rg_config_case(request, tmp_path):
    regex, options = request.param
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    config_file = tmp_path / "ripgrep.config"
    config_file.write_text(options)
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_text("needle\n")
    sibling = root / "other.txt"
    sibling.write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned rg config fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned rg config fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling, config_file)]
    return root, file, sibling, config_file, regex, before


def test_rg_config_backend_exact_selection(rg_config_case):
    # Arrange
    root, file, _, config_file, regex, _ = rg_config_case
    # Act
    files = _run_owned_rg_config("backend", root, config_file, regex)
    # Assert
    assert files == [str(file)]


def test_rg_config_preview_exact_selection(rg_config_case):
    # Arrange
    root, file, _, config_file, regex, _ = rg_config_case
    # Act
    result = _run_owned_rg_config("preview", root, config_file, regex)
    # Assert
    assert (result["summary"]["content_matches"], [entry["file"] for entry in result["contents"]]) == (1, [str(file)])


def test_rg_config_preview_preserves_owned_files(rg_config_case):
    # Arrange
    root, file, sibling, config_file, regex, before = rg_config_case
    # Act
    _run_owned_rg_config("preview", root, config_file, regex)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling, config_file)]
    # Assert
    assert after == before


def test_rg_config_apply_uses_rename_configuration(rg_config_case):
    # Arrange
    root, file, sibling, config_file, regex, before = rg_config_case
    # Act
    result = _run_owned_rg_config("apply", root, config_file, regex)
    preserved = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (sibling, config_file)]
    # Assert
    assert (result["error"], file.read_bytes(), preserved) == (None, b"REPLACED\n", before[1:])
