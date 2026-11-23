#!/usr/bin/env python3
# Timestamp: 2026-02-14
# File: scitex_dev/rename/filters.py

"""Filtering logic for bulk rename operations (PATH and SRC level).

Uses ripgrep (rg) when available for fast content matching,
falls back to Python glob + read_text otherwise.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .config import RenameConfig

_RG_PATH: str | None = shutil.which("rg")


def parse_csv_config(value: str) -> list[str]:
    """Parse comma-separated config string into list."""
    return [v.strip() for v in value.split(",") if v.strip()]


def should_exclude_path(path: Path, config: RenameConfig) -> bool:
    """Check if a path should be excluded based on config."""
    path_str = str(path)
    parts = path.parts

    # Must-excludes (strongest) - exact directory name match
    for exc in parse_csv_config(config.path_must_excludes):
        if exc in parts:
            return True

    # Standard excludes - exact directory name match
    for exc in parse_csv_config(config.path_excludes):
        if exc in parts:
            return True

    # Extra excludes from user
    for exc in config.extra_excludes:
        if exc in path_str:
            return True

    return False


def matches_include_extensions(path: Path, config: RenameConfig) -> bool:
    """Check if file extension matches include list."""
    includes = parse_csv_config(config.path_includes)
    if not includes:
        return True

    suffix = path.suffix.lstrip(".")
    name = path.name

    for inc in includes:
        if suffix == inc:
            return True
        if inc.startswith(".") and name.startswith(inc):
            return True
        if "*" in inc:
            import fnmatch

            if fnmatch.fnmatch(name, inc):
                return True

    return False


def matches_scope(path: Path, config: RenameConfig) -> bool:
    """Check if a file matches the scope glob pattern."""
    if not config.scope:
        return True
    import fnmatch

    return fnmatch.fnmatch(path.name, config.scope)


def _rg_find_content_matches(
    directory: str, config: RenameConfig, *, files_only: bool = False
) -> list[Path] | None:
    """Search with ripgrep, or list candidate paths. Returns None on failure."""

    if not _RG_PATH:
        return None

    mode = "--files" if files_only else "--files-with-matches"
    cmd = [_RG_PATH, "--no-config", mode, "--null", "--no-messages"]

    # Scope as glob filter
    if config.scope:
        cmd += ["--glob", config.scope]

    # Depth control
    if not config.recursive:
        cmd += ["--max-depth", "1"]

    # File listing preserves traversal/ignore rules without filtering regex text.
    if not files_only:
        if config.regex:
            cmd += ["--multiline", "--multiline-dotall"]
        else:
            cmd += ["--fixed-strings"]
        cmd.append("--regexp=" + config.pattern)

    # Exclude patterns
    for exc in parse_csv_config(config.path_excludes):
        cmd += ["--glob", f"!{exc}"]
    for exc in parse_csv_config(config.path_must_excludes):
        cmd += ["--glob", f"!{exc}"]
    for exc in config.extra_excludes:
        cmd += ["--glob", f"!*{exc}*"]

    cmd.append(directory)

    import subprocess  # noqa: E402 — local import to survive auto-linter

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode > 1:  # 1 = no matches (ok), >1 = error
            return None
        # Sort to guarantee deterministic ordering across preview / execute
        # passes. ripgrep with --threads >1 returns matches as workers
        # complete, so iteration order depends on FS racing — that drifted
        # the content `file_id` between passes and broke `skip_ids`.
        paths = sorted(Path(os.fsdecode(name)) for name in proc.stdout.split(b"\0") if name)
        return paths
    except (subprocess.TimeoutExpired, OSError):
        return None


def _matches_python_regex(path: Path, pattern: str) -> bool:
    """Match the same decoded, newline-normalized text used by replacement."""
    try:
        return re.search(pattern, path.read_text(errors="replace"), re.DOTALL) is not None
    except (OSError, UnicodeDecodeError):
        return False


def find_matching_files(
    directory: str, config: RenameConfig, need_content_match: bool = False
) -> list[Path]:
    """Find files matching the filtering criteria.

    Ripgrep searches literal text or lists regex candidates. Python regex
    matching uses the same text decoding as replacement. Falls back to glob.
    """
    # Keep ripgrep traversal; Python owns regex text semantics.
    if need_content_match:
        rg_results = _rg_find_content_matches(directory, config, files_only=config.regex)
        if rg_results is not None:
            # Apply Python-level filters rg can't handle. Extension filtering
            # only kicks in when no explicit `scope` glob is set — same as
            # the slow path below.
            return [
                p
                for p in rg_results
                if not p.is_symlink()
                and not should_exclude_path(p, config)
                and (config.scope or matches_include_extensions(p, config))
                and (not config.regex or _matches_python_regex(p, config.pattern))
            ]

    # Fallback: Python glob
    root = Path(directory)
    matching = []

    glob_pattern = config.scope or "*"
    glob_iter = (
        root.rglob(glob_pattern) if config.recursive else root.glob(glob_pattern)
    )
    for path in glob_iter:
        if not path.is_file() or path.is_symlink():
            continue
        if should_exclude_path(path, config):
            continue
        if not config.scope and not matches_include_extensions(path, config):
            continue
        if need_content_match:
            try:
                content = path.read_text(errors="replace")
                if config.regex:
                    if not re.search(config.pattern, content, re.DOTALL):
                        continue
                elif config.pattern not in content:
                    continue
            except (OSError, UnicodeDecodeError):
                continue
        matching.append(path)

    return sorted(matching)


def is_django_protected_line(line: str, pattern: str) -> bool:
    """Check if a line should be protected in Django-safe mode."""
    if re.search(r"db_table\s*=\s*['\"]", line):
        return True
    if re.search(r"(old_name|new_name)\s*=\s*['\"]", line):
        return True
    if re.search(r"related_name\s*=\s*['\"]", line):
        return True
    if re.search(r"objects\s*=\s*.*Manager", line):
        return True
    settings_patterns = (
        "INSTALLED_APPS",
        "DATABASES",
        "CACHES",
        "SECRET_KEY",
        "DEBUG",
        "ALLOWED_HOSTS",
        "MIDDLEWARE",
        "TEMPLATES",
    )
    stripped = line.lstrip()
    for sp in settings_patterns:
        if stripped.startswith(sp):
            return True
    if re.search(r"(django|Django).*\d+\.\d+", line):
        return True
    return False


def is_src_excluded(line: str, config: RenameConfig) -> bool:
    """Check if a line matches SRC-level exclusion patterns."""
    for exc in parse_csv_config(config.src_must_excludes):
        if exc in line:
            return True
    for exc in parse_csv_config(config.src_excludes):
        if exc in line:
            return True
    return False


# EOF
