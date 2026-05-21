#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rust-tool-backed file discovery for the audit suite.

Operator directive (2026-05-21): where the audit does recursive file
discovery, prefer the Rust `fd` tool over Python `os.walk` / `pathlib`
walks. `fd` honours `.gitignore` and is markedly faster on large trees.

Fail-loud contract: if `fd` is required and not on PATH, raise
`FdNotFoundError` with an explicit install hint. No silent fallback to
`find` or `pathlib.rglob` — the operator prefers a loud failure over a
quiet degrade.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

#: Install hint surfaced when `fd` is missing. Covers the common package
#: managers; `fd-find` is the Debian/Ubuntu name (binary is `fdfind`).
FD_INSTALL_HINT = (
    "the Rust `fd` tool is required for audit file discovery but was not "
    "found on PATH. Install it: `cargo install fd-find`, "
    "`brew install fd`, or `apt install fd-find` (Debian/Ubuntu installs "
    "the binary as `fdfind`)."
)


class FdNotFoundError(RuntimeError):
    """Raised when the required `fd` binary is not available on PATH."""


def fd_binary() -> str:
    """Return the resolved path to the `fd` binary, or raise loudly.

    Accepts the Debian/Ubuntu `fdfind` alias as a fallback name.

    Raises
    ------
    FdNotFoundError
        If neither `fd` nor `fdfind` is found on PATH.
    """
    for name in ("fd", "fdfind"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise FdNotFoundError(FD_INSTALL_HINT)


def fd_find_files(root: Path, *, glob: str = "*.py") -> list[Path]:
    """Recursively find files under `root` matching `glob`, via `fd`.

    Returns absolute `Path` objects, sorted for deterministic ordering.
    Mirrors `Path.rglob(glob)` semantics for plain file discovery
    (files only, recursive, gitignore-aware via `fd` defaults).

    Parameters
    ----------
    root
        Directory to search under.
    glob
        Glob pattern matched against file names (e.g. ``"*.py"``,
        ``"test_*.py"``).

    Raises
    ------
    FdNotFoundError
        If `fd` is not on PATH (fail-loud, no fallback).
    """
    binary = fd_binary()
    if not root.is_dir():
        return []
    proc = subprocess.run(
        [
            binary,
            "--type",
            "f",
            "--absolute-path",
            "--glob",
            glob,
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        # fd: 0 = matches, 1 = no matches (newer fd uses 0 either way);
        # anything else is a real error — surface it loudly.
        raise RuntimeError(
            f"fd failed under {root} (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return sorted(Path(line) for line in proc.stdout.splitlines() if line.strip())
