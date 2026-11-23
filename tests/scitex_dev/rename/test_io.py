"""Undecodable UTF-8 bytes round-trip through text edits and real writers."""

import locale
import subprocess

import pytest

from scitex_dev import execute_rename, preview_rename
from scitex_dev.rename.io import write_text

_BYTE_BODIES = [b"needle\n", b"alpha:\xce\xb1 needle \xce\xb2\n", b"note:\xef\xbf\xbd needle\n", b"prefix:\xff needle\n", b"needle suffix:\xfe\n", b"needle suffix:\xc3\n", b"\x80needle\xff\n"]


def _real_unprivileged_tee(args, *, input_data):
    subprocess.run(args, input=input_data, check=True, capture_output=True, timeout=10)


def _byte_fixture_state(files):
    return [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in files]


@pytest.fixture(params=[(piped, body) for piped in [False, True] for body in _BYTE_BODIES])
def byte_writer_case(request, tmp_path):
    assert locale.getencoding().lower() == "utf-8", "These byte fixtures specify a UTF-8 locale"
    piped, body = request.param
    file = tmp_path / "owned.txt"
    file.write_bytes(b"before\n")
    yield file, body.decode("utf-8", errors="surrogateescape"), body, piped


@pytest.fixture(params=[(regex, body) for regex in [False, True] for body in _BYTE_BODIES])
def byte_pipeline_case(request, tmp_path):
    assert locale.getencoding().lower() == "utf-8", "These byte fixtures specify a UTF-8 locale"
    regex, body = request.param
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_bytes(body)
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned byte text fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned byte text fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = _byte_fixture_state([file, sibling])
    yield root, file, sibling, regex, body, before


def test_byte_writer_roundtrips_original_bytes(byte_writer_case):
    # Arrange
    file, content, expected, piped = byte_writer_case
    # Act
    write_text(file, content, use_sudo=piped, runner=_real_unprivileged_tee if piped else None)
    # Assert
    assert file.read_bytes() == expected


def test_byte_pipeline_preview_preserves_fixture(byte_pipeline_case):
    # Arrange
    root, file, sibling, regex, _, before = byte_pipeline_case
    # Act
    preview_rename("needle", "CHANGED", directory=str(root), regex=regex)
    after = _byte_fixture_state([file, sibling])
    # Assert
    assert after == before


def test_byte_pipeline_changes_only_selected_token(byte_pipeline_case):
    # Arrange
    root, file, sibling, regex, body, before = byte_pipeline_case
    # Act
    result = execute_rename("needle", "CHANGED", directory=str(root), regex=regex)
    sibling_after = _byte_fixture_state([sibling])[0]
    # Assert
    assert (result.error, result.summary["content_matches"], file.read_bytes(), sibling_after) == (None, 1, body.replace(b"needle", b"CHANGED"), before[1])
