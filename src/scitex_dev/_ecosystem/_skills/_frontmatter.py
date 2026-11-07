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
    import re

    if re.search(rf"^{key}:", content, re.MULTILINE):
        return re.sub(
            rf"^({key}:\s*).*$",
            rf"\g<1>{value}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    # Insert before the closing ``---`` of the frontmatter block. If the
    # file has no frontmatter (legacy), prepend a minimal block.
    if content.startswith("---\n"):
        # Find the second ``---\n`` and insert before it.
        end = content.find("\n---\n", 4)
        if end != -1:
            return content[: end + 1] + f"{key}: {value}\n" + content[end + 1 :]
    # No frontmatter at all — prepend a minimal one.
    return f"---\n{key}: {value}\n---\n\n" + content
