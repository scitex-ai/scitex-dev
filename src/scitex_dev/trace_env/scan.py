#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/trace_env/scan.py

"""MODE 1 — static scan: find where env vars are ASSIGNED.

Walks every environment-definition surface (current process env, shell
init files, direnv, tmux global env), records each ``file:line``
assignment site with WORD-BOUNDARY matching, and redacts secret-shaped
values. Pure and testable: ``home``, ``cwd`` and ``environ`` are all
injectable so tests never touch the real ``$HOME``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import (
    Assignment,
    TraceEnvResult,
    VarReport,
    assignment_regex,
    is_secret_shaped,
    redact,
)

# (surface-label, path-or-glob). ``**`` entries are walked recursively.
_SHELL_INIT = [
    "~/.bashrc",
    "~/.bash_profile",
    "~/.profile",
    "~/.zshrc",
    "~/.zprofile",
    "~/.bash.d/**",
    "~/.direnvrc",
    "~/.config/direnv/**",
]
_ETC = [
    "/etc/profile",
    "/etc/profile.d/**",
    "/etc/bash.bashrc",
    "/etc/zsh/**",
]


def _expand(spec: str, home: Path) -> Path:
    """Expand a leading ``~`` against the injected ``home``."""
    if spec == "~" or spec.startswith("~/"):
        return home / spec[2:] if spec.startswith("~/") else home
    return Path(spec)


def _iter_files(spec_paths: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    """Resolve a list of (surface, path/glob-root) into concrete files.

    A path ending ``**`` is walked recursively (all files, incl. ``.src``).
    Missing paths are skipped silently.
    """
    out: list[tuple[str, Path]] = []
    for surface, p in spec_paths:
        if p.name == "**":
            root = p.parent
            if root.is_dir():
                out.extend(
                    (surface, f) for f in sorted(root.rglob("*")) if f.is_file()
                )
        elif p.is_file():
            out.append((surface, p))
    return out


def _envrc_chain(cwd: Path) -> list[tuple[str, Path]]:
    """Every ``.envrc`` walking up from ``cwd`` to the filesystem root."""
    found: list[tuple[str, Path]] = []
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".envrc"
        if candidate.is_file():
            found.append(("direnv", candidate))
    return found


def _redact_line(name: str, stripped: str) -> str:
    """Redact the RHS of an assignment line if the var is secret-shaped.

    ``stripped`` is a matched line (guaranteed to contain ``=``). The
    first ``=`` is the assignment operator since the var name — which
    cannot contain ``=`` — precedes it.
    """
    if not is_secret_shaped(name) or "=" not in stripped:
        return stripped
    eq = stripped.index("=")
    rhs = stripped[eq + 1 :].strip().strip("'\"")
    return stripped[: eq + 1] + f"<redacted: {len(rhs)} chars>"


def _scan_file(surface: str, path: Path, names: list[str]) -> list[Assignment]:
    """Collect assignment sites for every ``name`` in one file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: list[Assignment] = []
    regexes = [(n, assignment_regex(n)) for n in names]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        for name, rx in regexes:
            if not rx.search(raw):
                continue
            hits.append(
                Assignment(
                    var=name,
                    surface=surface,
                    file=str(path),
                    line=lineno,
                    text=_redact_line(name, raw.strip()),
                )
            )
    return hits


def _tmux_global_env(names: list[str]) -> tuple[list[Assignment], bool]:
    """Parse ``tmux show-environment -g``; skip gracefully if unavailable."""
    try:
        proc = subprocess.run(
            ["tmux", "show-environment", "-g"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return [], False
    if proc.returncode != 0:
        return [], True
    hits: list[Assignment] = []
    regexes = [(n, assignment_regex(n)) for n in names]
    for lineno, raw in enumerate(proc.stdout.splitlines(), start=1):
        for name, rx in regexes:
            if rx.search(raw):
                hits.append(
                    Assignment(
                        var=name,
                        surface="tmux",
                        file="tmux show-environment -g",
                        line=lineno,
                        text=_redact_line(name, raw.strip()),
                    )
                )
    return hits, True


def scan_env_vars(
    names: list[str],
    home: Path | None = None,
    cwd: Path | None = None,
    environ: dict[str, str] | None = None,
    include_etc: bool = True,
    include_tmux: bool = True,
    extra_files: list[str] | None = None,
) -> TraceEnvResult:
    """Static scan for where each name in ``names`` is assigned.

    Returns a :class:`TraceEnvResult` with one :class:`VarReport` per
    name: whether it is currently set (redacted value if secret-shaped)
    plus every ``file:line`` assignment site across the scanned surfaces.
    """
    home = home or Path.home()
    cwd = cwd or Path.cwd()
    environ = os.environ if environ is None else environ

    specs: list[tuple[str, Path]] = [
        ("shell-init", _expand(s, home)) for s in _SHELL_INIT
    ]
    if include_etc:
        specs += [("shell-init", Path(s)) for s in _ETC]
    for extra in extra_files or []:
        specs.append(("shell-init", _expand(extra, home)))

    files = _iter_files(specs) + _envrc_chain(cwd)

    per_var: dict[str, list[Assignment]] = {n: [] for n in names}
    for surface, path in files:
        for a in _scan_file(surface, path, names):
            per_var[a.var].append(a)

    tmux_ok = False
    if include_tmux:
        tmux_hits, tmux_ok = _tmux_global_env(names)
        for a in tmux_hits:
            per_var[a.var].append(a)

    variables = []
    for name in names:
        raw_val = environ.get(name)
        variables.append(
            VarReport(
                name=name,
                currently_set=raw_val is not None,
                current_value=redact(name, raw_val),
                secret_shaped=is_secret_shaped(name),
                assignments=per_var[name],
            )
        )

    return TraceEnvResult(
        variables=variables,
        scanned_files=len(files),
        tmux_available=tmux_ok,
        mode="scan",
    )


# EOF
