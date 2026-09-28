#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keep ``~/.scitex`` managed by git so specs stay provable.

Problem
-------
Lifecycle gates (e.g. the agent spec-authority check) need a provable source
for every spec: a git repo, a clean HEAD, a digest. But ``sac agents create``
and its siblings scaffold spec directories straight into ``~/.scitex``,
which has historically been a plain directory — so every created spec is
authority-less by construction and every launch fails closed.

What this module does
---------------------
:func:`ensure_dotscitex_managed_by_git` adopts an EXISTING ``~/.scitex``
(resp. initialises a missing one) into a git repository with a managed
``.gitignore`` block that encodes the cross-package placement contract:

* ``.scitex/<pkg>/runtime/`` holds processes' live state (logs, sockets,
  session transcripts, pid files, caches). It is NEVER tracked, for any
  package, present or future — pattern-based, no per-package knowledge.
* Large artefacts (images, archives, databases) are never tracked either.
* Only package-declared track globs (specs, configs) are committable, and
  the default is deny: anything not matched stays untracked, so a commit
  can never sweep live secrets or caches into history.

Compatibility migration
-----------------------
Files that already live OUTSIDE ``<pkg>/runtime/`` but belong there (known
runtime filenames such as ``session.jsonl``, ``*.log``, ``*.pid``) are
MOVED under ``<pkg>/runtime/`` with a symlink left at the old path, so
running processes and tools keep working while history stays clean. The
move set is reported, never silent.

Fail-loud: missing ``git``, unresolvable home, or any git error raises.
This function never falls back to "unmanaged but pretending".
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, Mapping

#: Directory name managed under the user's home.
DOTSCITEX_DIRNAME = ".scitex"

#: Filenames that are runtime state wherever they appear (mirrors the
#: placement contract; the migration moves them under ``<pkg>/runtime/``).
_RUNTIME_FILENAMES = frozenset(
    {
        "session.jsonl",
        "heartbeat.json",
        "pid",
        "stdout.log",
        "stderr.log",
        "boot.stdout.log",
        "boot.stderr.log",
    }
)

#: Suffixes treated as runtime/large artefacts wherever they appear.
_RUNTIME_SUFFIXES = (".log", ".pid", ".sock", ".sif", ".tar.gz", ".db-wal", ".db-shm")

#: Marker lines delimiting the block this module owns inside .gitignore.
_BLOCK_BEGIN = "# >>> scitex-dev: managed block (dotscitex_git) >>>"
_BLOCK_END = "# <<< scitex-dev: managed block (dotscitex_git) <<<"


def _run_git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"ensure_dotscitex_managed_by_git: git is unavailable: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"ensure_dotscitex_managed_by_git: "
            f"git {' '.join(args)} failed in {root}: "
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    return proc.stdout.strip()


def _managed_block(track: Iterable[str], extra_ignore: Iterable[str] = ()) -> str:
    """Build the .gitignore block: runtime contract + track negations."""
    lines = [_BLOCK_BEGIN]
    lines.append("# Placement contract: <pkg>/runtime/ is NEVER tracked.")
    lines.append("*/runtime/")
    lines.append("**/runtime/**")
    lines.append("# Large artefacts are never tracked either.")
    lines.append("*.sif")
    lines.append("*.tar.gz")
    lines.append("*.tgz")
    lines.append("*.db-wal")
    lines.append("*.db-shm")
    lines.append("*.sock")
    lines.append("*.pid")
    lines.append("*.log")
    lines.append("session.jsonl")
    lines.append("heartbeat.json")
    for pattern in sorted(set(extra_ignore)):
        lines.append(pattern)
    lines.append("# Default deny: only package-declared tracks commit.")
    lines.append("*")
    lines.append("!*/")
    lines.append("!.gitignore")
    for pattern in sorted(set(track)):
        lines.append(f"!{pattern}")
    lines.append(_BLOCK_END)
    return "\n".join(lines) + "\n"


def _merge_gitignore(path: Path, block: str) -> bool:
    """Merge our block into .gitignore, preserving user lines. Returns changed."""
    existing = path.read_text() if path.is_file() else ""
    if _BLOCK_BEGIN in existing and _BLOCK_END in existing:
        start = existing.index(_BLOCK_BEGIN)
        end = existing.index(_BLOCK_END) + len(_BLOCK_END)
        new = existing[:start] + block + existing[end:].lstrip("\n")
        if new == existing:
            return False
        path.write_text(new if new.endswith("\n") else new + "\n")
        return True
    new = (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block
    if new == existing:
        return False
    path.write_text(new)
    return True


def _migrate_runtime_files(root: Path) -> list[str]:
    """Move stray runtime files under ``<pkg>/runtime/``, leaving symlinks.

    The placement contract is per top-level package dir: a runtime file at
    ``<pkg>/<rest...>`` moves to ``<pkg>/runtime/<rest...>`` (relative path
    preserved, so per-agent trees stay separated) with a symlink left at
    the old path. Files already under any ``runtime/`` component, inside
    ``.git``, or that are dirs/symlinks are never touched. An existing
    target is never clobbered. Returns the moved paths (``old -> new``).
    """
    moved: list[str] = []
    pkgs = sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and p.name != ".git")
    for pkg in pkgs:
        runtime_base = pkg / "runtime"
        for child in sorted(pkg.rglob("*")):
            if child.is_dir() or child.is_symlink():
                continue
            if "runtime" in child.relative_to(pkg).parts:
                continue
            name = child.name
            is_runtime = name in _RUNTIME_FILENAMES or name.endswith(_RUNTIME_SUFFIXES)
            if not is_runtime:
                continue
            rel = child.relative_to(pkg)
            target = runtime_base / rel
            if target.exists() or target.is_symlink():
                continue  # already migrated; never clobber
            target.parent.mkdir(parents=True, exist_ok=True)
            child.rename(target)
            child.symlink_to(target)
            moved.append(f"{pkg.name}/{rel} -> {pkg.name}/runtime/{rel}")
    return moved


def ensure_dotscitex_managed_by_git(
    home: str | Path | None = None,
    *,
    track: Iterable[str] = (),
    extra_ignore: Iterable[str] = (),
    commit: bool = True,
    commit_message: str = "scitex-dev: manage .scitex (specs + config)",
    actor_name: str = "scitex-dev",
    actor_email: str = "scitex-dev@local",
) -> dict:
    """Adopt ``~/.scitex`` into git management; return the outcome envelope.

    Idempotent: safe to call on every launch path. A second call with no
    changes stages and commits nothing.
    """
    base = Path(os.path.expanduser(home) if home else "~").expanduser()
    root = base / DOTSCITEX_DIRNAME
    root.mkdir(parents=True, exist_ok=True)

    initialized = not (root / ".git").exists()
    if initialized:
        _run_git(root, "init", "-q")

    track_list = sorted(set(track))
    gitignore_changed = _merge_gitignore(
        root / ".gitignore", _managed_block(track_list, extra_ignore)
    )
    moved = _migrate_runtime_files(root)

    _run_git(root, "add", "-A")
    status = _run_git(root, "status", "--porcelain")
    committed = False
    if status and commit:
        _run_git(root, "-c", f"user.name={actor_name}", "-c", f"user.email={actor_email}",
                 "commit", "-q", "-m", commit_message)
        committed = True
    try:
        head = _run_git(root, "rev-parse", "HEAD")
    except RuntimeError:
        head = ""  # fresh repo, nothing trackable yet: initialized, uncommitted
    return {
        "root": str(root),
        "initialized": initialized,
        "gitignore_changed": gitignore_changed,
        "runtime_migrated": moved,
        "committed": committed,
        "head": head,
        "clean": not bool(_run_git(root, "status", "--porcelain")),
    }
