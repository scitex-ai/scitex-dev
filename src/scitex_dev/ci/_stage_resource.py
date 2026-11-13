"""Stage pinned CI resources; callers own trust, download and root lifecycle.

This internal stdlib-only transport accepts no runtime or publishing admission.
The expected digest must come from the caller's reviewed source contract.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat

_MAX_BYTES = 1024 * 1024


def _read_resource(source: Path, expected: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("expected SHA-256 must be 64 lowercase hex characters")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_BYTES:
            raise ValueError("resource must be a regular file of at most 1 MiB")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(_MAX_BYTES + 1)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or len(raw) > _MAX_BYTES:
            raise ValueError("resource changed while reading")
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("resource SHA-256 differs from the reviewed digest")
        return raw
    finally:
        os.close(fd)


def _stage_resource(source: Path, destination: Path, expected: str) -> dict:
    """Create one private resource without replacing an existing destination."""
    source, destination = Path(source), Path(destination)
    if not source.is_absolute() or not destination.is_absolute():
        raise ValueError("resource and destination paths must be absolute")
    if destination.name in {"", ".", ".."}:
        raise ValueError("destination must name a new file")
    raw = _read_resource(source, expected)
    parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = None
    try:
        before = os.fstat(parent)
        if before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o700:
            raise ValueError("destination parent must be caller-owned mode 0700")
        fd = os.open(
            destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=parent,
        )
        created = os.fstat(fd)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        current = os.stat(destination.parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_uid, current.st_mode) != (
            before.st_dev, before.st_ino, before.st_uid, before.st_mode
        ):
            raise ValueError("destination parent identity changed")
        return {"path": str(destination), "sha256": expected, "bytes": len(raw)}
    except BaseException:
        if created is not None:
            current = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                os.unlink(destination.name, dir_fd=parent)
        raise
    finally:
        os.close(parent)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        _stage_resource(args.source, args.destination, args.sha256)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    _main()
