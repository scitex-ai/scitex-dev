"""Commit/relevant-edit gate using the project auditor's exact source checker."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ._index import git as _git
from ._index import staged_sources
from ._project import inspect_interfaces


def _commit_repo(command, cwd):
    """Recognize ordinary git commit invocations without executing shell code."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    effective = Path(cwd)
    for index, token in enumerate(tokens):
        command_start = index == 0 or tokens[index - 1] in {"&&", ";", "||", "|", "("}
        if token == "cd" and command_start and index + 1 < len(tokens):
            target = Path(tokens[index + 1])
            effective = target if target.is_absolute() else effective / target
        if token != "git" or not command_start:
            continue
        selected = effective
        cursor = index + 1
        while cursor < len(tokens):
            part = tokens[cursor]
            if part == "-C" and cursor + 1 < len(tokens):
                target = Path(tokens[cursor + 1])
                selected = target if target.is_absolute() else selected / target
                cursor += 2
            elif part == "-c" and cursor + 1 < len(tokens):
                cursor += 2
            elif part.startswith("-"):
                cursor += 1
            else:
                if part == "commit":
                    return selected.resolve()
                break
    return None


def _relevant(path):
    parts = Path(path).parts
    return (
        path == "pyproject.toml"
        or path == ".scitex/dev/config.yaml"
        or ("_skills" in parts)
        or (
            path.endswith(".py")
            and any(
                item in {"__init__.py", "api.py", "_api.py", "mcp.py", "_mcp.py"}
                or item.startswith(("_mcp", "mcp_", "_api", "api_"))
                or item in {"_cli", "cli"}
                for item in parts
            )
        )
    )


def check_payload(payload):
    """Inspect only the caller's repository; never import or execute its code."""
    cwd = Path(payload.get("cwd") or Path.cwd()).resolve()
    data = payload.get("tool_input") or payload.get("arguments") or {}
    event = payload.get("hook_event_name", "pre-tool-use")
    post = event in {"PostToolUse", "post_tool_call", "post-tool-use"}
    command = data.get("command", "")
    target = None if post else _commit_repo(command, cwd)
    if target is None and not post:
        return []  # proposed edits are checked after they exist, not against old bytes
    try:
        root = _git(target or cwd, "rev-parse", "--show-toplevel")
        if root.returncode:
            return []
        repo = Path(root.stdout.decode().strip()).resolve()
        if post:
            paths = set()
            for args in (
                ("diff", "--name-only", "--diff-filter=ACMR", "-z", "HEAD"),
                ("ls-files", "--others", "--exclude-standard", "-z"),
            ):
                result = _git(repo, *args)
                if result.returncode:
                    return [
                        "PS-IF-001: cannot enumerate relevant interface source changes"
                    ]
                paths.update(result.stdout.decode().split("\0"))
            if not any(_relevant(path) for path in paths if path):
                return []
        overlays = None if post else staged_sources(repo)
        return [
            f"{item.rule}: {item.path}:{item.line}: {item.detail}"
            for item in inspect_interfaces(repo, overlays=overlays)
            if item.severity == "E"
        ]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [f"PS-IF-001: cannot verify interface contract ({type(exc).__name__})"]
