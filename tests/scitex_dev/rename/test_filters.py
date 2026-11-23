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
