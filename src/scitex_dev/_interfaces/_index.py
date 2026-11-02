"""Bounded staged-source overlays; never execute staged package code."""

from __future__ import annotations

import os
import subprocess
from pathlib import PurePosixPath

from ._source import UnprovenBinding


def git(repo, *args, input=None):
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        input=input,
        timeout=10,
        env=env,
        check=False,
    )


def staged_sources(repo):
    """Read only regular index metadata/Python/skill blobs, at most 64 MiB."""
    listing = git(repo, "ls-files", "--stage", "-z")
    if listing.returncode:
        raise UnprovenBinding("cannot enumerate staged interface source")
    selected = []
    overlays = {}
    for entry in listing.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        path = path.decode("utf-8")
        if not (
            path.endswith((".py", "/SKILL.md"))
            or path in {"pyproject.toml", ".scitex/dev/config.yaml"}
        ):
            continue
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise UnprovenBinding("index source path is outside the repository")
        mode, oid, stage = metadata.split()
        if stage != b"0":
            raise UnprovenBinding("unmerged interface source is not a commit candidate")
        if mode not in {b"100644", b"100755"}:
            overlays[path] = None
            continue
        selected.append((path, oid))
    ids = b"".join(oid + b"\n" for _path, oid in selected)
    sizes = git(repo, "cat-file", "--batch-check", input=ids)
    if sizes.returncode:
        raise UnprovenBinding("cannot inspect staged source sizes")
    rows = sizes.stdout.splitlines()
    if len(rows) != len(selected):
        raise UnprovenBinding("staged source size inventory changed")
    expected = []
    for (_path, oid), row in zip(selected, rows):
        fields = row.split()
        if len(fields) != 3 or fields[0] != oid or fields[1] != b"blob":
            raise UnprovenBinding("staged source is not an attested Git blob")
        size = int(fields[2])
        if not 0 <= size <= 4 * 1024 * 1024:
            raise UnprovenBinding("staged source exceeds the 4 MiB member limit")
        expected.append(size)
    if sum(expected) > 64 * 1024 * 1024:
        raise UnprovenBinding("staged interface source exceeds the 64 MiB total limit")
    blobs = git(repo, "cat-file", "--batch", input=ids)
    if blobs.returncode:
        raise UnprovenBinding("cannot read staged source blobs")
    offset = 0
    for (path, oid), size in zip(selected, expected):
        end = blobs.stdout.find(b"\n", offset)
        header = blobs.stdout[offset:end].split()
        if end < 0 or header != [oid, b"blob", str(size).encode()]:
            raise UnprovenBinding("staged source blob header changed")
        offset = end + 1
        value = blobs.stdout[offset : offset + size]
        offset += size
        if len(value) != size or blobs.stdout[offset : offset + 1] != b"\n":
            raise UnprovenBinding("truncated staged source blob")
        overlays[path] = value.decode("utf-8")
        offset += 1
    if offset != len(blobs.stdout):
        raise UnprovenBinding("unexpected staged source bytes")
    return overlays
