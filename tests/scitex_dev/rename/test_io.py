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


_LINK_OPERAND_TARGETS = ["plain-target", "-target", "--help", "--version", "-s", "with space", "greek-α", "line\nbreak"]


def _real_unprivileged_ln(args):
    from pathlib import Path
    subprocess.run(args, cwd=Path(args[-1]).parent, check=True, capture_output=True, timeout=10)


@pytest.fixture(params=[(piped, target) for piped in [False, True] for target in _LINK_OPERAND_TARGETS])
def link_operand_case(request, tmp_path):
    piped, target = request.param
    file = tmp_path / target
    file.write_bytes(b"owned target sentinel\n")
    sibling = tmp_path / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    link = tmp_path / "owned-link"
    before = _byte_fixture_state([file, sibling])
    yield link, target, piped, [file, sibling], before


def test_link_operand_literal_target_and_sentinels(link_operand_case):
    # Arrange
    import os
    from scitex_dev.rename.io import symlink_to
    link, target, piped, protected, before = link_operand_case
    # Act
    symlink_to(link, target, use_sudo=piped, runner=_real_unprivileged_ln if piped else None)
    # Assert
    assert (os.readlink(link), _byte_fixture_state(protected)) == (target, before)


@pytest.fixture(params=[(operation, piped, name) for operation in ["unlink", "rmdir"] for piped in [False, True] for name in ["ordinary", "--help", "--version", "-x"]])
def removal_operand_case(request, tmp_path):
    operation, piped, name = request.param
    root = tmp_path / "owned-removal"
    root.mkdir()
    victim = root / name
    if operation == "unlink":
        victim.write_bytes(b"owned removal target\n")
    else:
        victim.mkdir()
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated outside\n")
    before = _byte_fixture_state([sibling, outside])
    yield root, victim, operation, piped, name, [sibling, outside], before


def test_removal_operand_literal_path_and_sentinels(removal_operand_case):
    # Arrange
    import sys
    root, victim, operation, piped, name, protected, before = removal_operand_case
    code = """
from pathlib import Path
import subprocess,sys
from scitex_dev.rename.io import unlink_path,rmdir
operation,name,piped=sys.argv[1:]
def real_runner(args):
    subprocess.run(args,check=True,capture_output=True,timeout=10)
fn=unlink_path if operation=='unlink' else rmdir
fn(Path(name),use_sudo=piped=='True',runner=real_runner if piped=='True' else None)
"""
    # Act
    subprocess.run([sys.executable, "-I", "-c", code, operation, name, str(piped)], cwd=root, check=True, capture_output=True, timeout=15)
    # Assert
    assert (victim.exists() or victim.is_symlink(), _byte_fixture_state(protected)) == (False, before)


@pytest.fixture(params=[(piped, name) for piped in [False, True] for name in ["ordinary", "--help", "--version", "-x", "-", "with space", "greek-α", "line\nbreak"]])
def writer_operand_case(request, tmp_path):
    piped, name = request.param
    root = tmp_path / "owned-writer"
    root.mkdir()
    file = root / name
    file.write_bytes(b"before\n")
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated outside\n")
    before = _byte_fixture_state([sibling, outside])
    yield root, file, piped, name, [sibling, outside], before


def test_writer_operand_literal_path_and_sentinels(writer_operand_case):
    # Arrange
    import sys
    root, file, piped, name, protected, before = writer_operand_case
    code = r"""
from pathlib import Path
import subprocess,sys
from scitex_dev.rename.io import write_text
name,piped=sys.argv[1:]
def real_runner(args,*,input_data):
    subprocess.run(args,input=input_data,check=True,capture_output=True,timeout=10)
write_text(Path(name),"CHANGED α\n",use_sudo=piped=='True',runner=real_runner if piped=='True' else None)
"""
    # Act
    subprocess.run([sys.executable, "-I", "-c", code, name, str(piped)], cwd=root, check=True, capture_output=True, timeout=15)
    # Assert
    assert (file.read_bytes(), _byte_fixture_state(protected)) == ("CHANGED α\n".encode("utf-8"), before)


@pytest.fixture(params=[(piped, parents, name) for piped in [False, True] for parents in [False, True] for name in ["ordinary", "--help", "--version", "-x"]])
def mkdir_operand_case(request, tmp_path):
    piped, parents, name = request.param
    root = tmp_path / "owned-mkdir"
    root.mkdir()
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated outside\n")
    before = _byte_fixture_state([sibling, outside])
    yield root, piped, parents, name, [sibling, outside], before


def test_mkdir_operand_literal_path_and_sentinels(mkdir_operand_case):
    # Arrange
    import sys
    root, piped, parents, name, protected, before = mkdir_operand_case
    code = """
from pathlib import Path
import subprocess,sys
from scitex_dev.rename.io import mkdir
name,piped,parents=sys.argv[1:]
def real_runner(args):
    subprocess.run(args,check=True,capture_output=True,timeout=10)
mkdir(Path(name),parents=parents=='True',use_sudo=piped=='True',runner=real_runner if piped=='True' else None)
"""
    # Act
    subprocess.run([sys.executable, "-I", "-c", code, name, str(piped), str(parents)], cwd=root, check=True, capture_output=True, timeout=15)
    # Assert
    assert ((root / name).is_dir(), _byte_fixture_state(protected)) == (True, before)


@pytest.fixture(params=[(piped, position, name) for piped in [False, True] for position in ["source", "destination"] for name in ["ordinary", "--help", "--version", "-x"]])
def move_operand_case(request, tmp_path):
    piped, position, name = request.param
    root = tmp_path / "owned-move"
    root.mkdir()
    source_name = name if position == "source" else "source.txt"
    destination_name = name if position == "destination" else "destination.txt"
    source = root / source_name
    source.write_bytes(b"owned move payload\n")
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated outside\n")
    before = (_byte_fixture_state([source])[0], _byte_fixture_state([sibling, outside]))
    yield root, piped, source_name, destination_name, [sibling, outside], before


def test_move_operand_literal_paths_and_sentinels(move_operand_case):
    # Arrange
    import sys
    root, piped, source_name, destination_name, protected, before = move_operand_case
    code = """
from pathlib import Path
import subprocess,sys
from scitex_dev.rename.io import rename_path
source,destination,piped=sys.argv[1:]
def real_runner(args):
    subprocess.run(args,check=True,capture_output=True,timeout=10)
rename_path(Path(source),Path(destination),use_sudo=piped=='True',runner=real_runner if piped=='True' else None)
"""
    # Act
    subprocess.run([sys.executable, "-I", "-c", code, source_name, destination_name, str(piped)], cwd=root, check=True, capture_output=True, timeout=15)
    destination = root / destination_name
    observed_destination = _byte_fixture_state([destination])[0] if destination.exists() else None
    # Assert
    assert ((root / source_name).exists(), observed_destination, _byte_fixture_state(protected)) == (False, before[0], before[1])
