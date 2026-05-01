"""Smoke tests for scitex_dev.app._protocol."""

from __future__ import annotations

from scitex_dev.app._protocol import FilesBackend
from scitex_dev.app._filesystem import FileSystemBackend


def test_filesystem_backend_satisfies_protocol(tmp_path):
    """FileSystemBackend is structurally a FilesBackend (runtime_checkable)."""
    fs = FileSystemBackend(tmp_path)
    assert isinstance(fs, FilesBackend)


def test_protocol_lists_all_methods():
    """All 7 methods documented in the protocol exist on FilesBackend."""
    expected = {"read", "write", "list", "exists", "delete", "rename", "copy"}
    have = {m for m in dir(FilesBackend) if not m.startswith("_")}
    assert expected.issubset(have), f"missing: {expected - have}"
