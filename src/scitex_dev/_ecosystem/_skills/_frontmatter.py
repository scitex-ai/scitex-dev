"""YAML frontmatter utilities for skill markdown files."""

from __future__ import annotations

import re
from pathlib import Path


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a markdown file."""
    try:
        text = path.read_text()
    except (OSError, UnicodeError):
        return {}

    match = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", text, re.DOTALL)
    if match is None:
        return {}

    import yaml

    try:
        metadata = yaml.safe_load(match.group(1) + "\n")
    except yaml.YAMLError:
        return {}

    if not isinstance(metadata, dict):
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _stamp_frontmatter_field(content: str, key: str, value: str) -> str:
    """Set or insert a field in a markdown file's YAML frontmatter.

    Used at ``skills export`` time to stamp every cached leaf with the
    exporting package's ``version`` and ``exported_via`` fields. The
    runtime drift check (``skills get`` / ``skills list``) reads these
    stamps to compare against ``importlib.metadata.version()``.
    """
    block = re.match(
        r"\A---[ \t]*(?P<newline>\r?\n)(?P<header>.*?)"
        r"(?P<closing>^---[ \t]*(?:\r?\n|\Z))",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if block is None:
        return f"---\n{key}: {value}\n---\n\n" + content

    # Scope replacements to metadata: body examples can contain the same key.
    header, replaced = re.subn(
        rf"^({re.escape(key)}:[ \t]*)[^\r\n]*",
        lambda field: f"{field[1]}{value}",
        block["header"],
        count=1,
        flags=re.MULTILINE,
    )
    if not replaced:
        header += f"{key}: {value}{block['newline']}"
    return content[: block.start("header")] + header + content[block.start("closing") :]
