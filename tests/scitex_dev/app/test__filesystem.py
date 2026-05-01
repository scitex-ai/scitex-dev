"""Smoke tests for scitex_dev.app._filesystem."""

from __future__ import annotations

import pytest

from scitex_dev.app._filesystem import FileSystemBackend


def test_filesystem_backend_roundtrip(tmp_path):
    """FileSystemBackend round-trips read/write/exists/delete."""
    fs = FileSystemBackend(tmp_path)
    assert fs.root == tmp_path.resolve()
    assert fs.exists("nope.txt") is False

    fs.write("sub/hello.txt", "hi")
    assert fs.exists("sub/hello.txt")
    assert fs.read("sub/hello.txt") == "hi"

    fs.write("sub/bytes.bin", b"\x00\x01\x02")
    assert fs.read("sub/bytes.bin", binary=True) == b"\x00\x01\x02"

    listed = fs.list("sub")
    assert "sub/hello.txt" in listed and "sub/bytes.bin" in listed

    fs.copy("sub/hello.txt", "sub/hello2.txt")
    assert fs.exists("sub/hello2.txt")

    fs.rename("sub/hello2.txt", "sub/hello3.txt")
    assert fs.exists("sub/hello3.txt") and not fs.exists("sub/hello2.txt")

    fs.delete("sub/hello.txt")
    assert not fs.exists("sub/hello.txt")


def test_filesystem_backend_traversal_blocked(tmp_path):
    """Path traversal outside root raises ValueError."""
    fs = FileSystemBackend(tmp_path)
    with pytest.raises(ValueError, match="traversal"):
        fs.read("../../../etc/passwd")


def test_filesystem_backend_missing_file(tmp_path):
    fs = FileSystemBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        fs.read("does_not_exist.txt")
