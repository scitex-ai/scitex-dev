"""Shared regexes + section helpers for the README-structure rule family.

Split out of the legacy-oversized ``_check_readme_structure.py`` (775
lines, over this repo's own 512-line file cap) so each rule-family lives
in its own small module — the same shape as
``_cli/audit/_summary/_gui_group.py`` / ``_dev_group.py``.

This module holds only the pieces MORE THAN ONE rule-family needs:
section lookup, the visual/diagram content predicates, and the
``<details>`` / badges-block strippers.
"""

from __future__ import annotations

import re
from pathlib import Path


# Read the WHOLE README. A 16 KiB head-slice used to produce PS-142
# false positives ("missing mandatory `## Architecture`") on packages
# whose READMEs grew past that budget — the section was present, the
# checker simply could not see it (scitex-storage, 23 KB). A check that
# cannot see the whole input MUST NOT report absence. The sibling
# `_check_readme_sections.py` already made exactly this fix for PS-107;
# this mirrors its constant and rationale. 1 MiB is a sanity bound, not
# a working window — every SciTeX README is well under it.
README_MAX_BYTES = 1024 * 1024
MIN_README_BYTES = 200


def read_readme(readme: Path) -> str | None:
    """Return the README text, or None when it is absent/unreadable/stub.

    Reads up to ``README_MAX_BYTES`` — effectively the whole file for any
    real README. See the constant's note: this deliberately is NOT a
    working window, so section-absence findings are trustworthy.
    """
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")[:README_MAX_BYTES]
    except OSError:
        return None
    if len(text) < MIN_README_BYTES:
        return None
    return text


# --- section headers ------------------------------------------------------

# Canonical H2 section names (lowercased keys), with the regex matching their
# header line (line starting with `##` and the section name).
SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "problem_and_solution": re.compile(
        r"^##\s+Problem(?:\s+and|s\s+and)\s+Solutions?\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "installation": re.compile(r"^##\s+Installation\b", re.MULTILINE | re.IGNORECASE),
    "architecture": re.compile(
        r"^##\s+(?:Architecture|How\s+it\s+works|How\s+It\s+Works)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "interfaces": re.compile(
        r"^##\s+(?:Three|Four|Five|Six|\d+)\s+Interfaces\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "demo": re.compile(r"^##\s+Demo(?:s|nstration)?\b", re.MULTILINE | re.IGNORECASE),
    "quick_start": re.compile(
        r"^##\s+(?:Quick\s*Start|Quickstart)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "part_of_scitex": re.compile(
        r"^##\s+Part\s+of\s+SciTeX\b", re.MULTILINE | re.IGNORECASE
    ),
    # PS-152: standalone `## Problem` / `## Solution` headings (NOT the
    # canonical merged `## Problem and Solution`). The negative lookahead
    # rules out the merged form so this only fires on the split variants.
    "problem_only": re.compile(
        r"^##\s+Problems?(?!\s+(?:and|s\s+and)\s+Solutions?)\b",
        re.MULTILINE | re.IGNORECASE,
    ),
    "solution_only": re.compile(
        r"^##\s+Solutions?\b",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Canonical order (skipped sections collapse — only the relative order matters).
# Updated 2026-05: Quick Start now sits between Problem-and-Solution and
# Installation (replaces the old role of the primary Demo block).
CANONICAL_ORDER = [
    "problem_and_solution",
    "quick_start",
    "demo",
    "installation",
    "architecture",
    "interfaces",
    "part_of_scitex",
]


# --- shared content regexes ------------------------------------------------

# Visual-content patterns inside a section body (PS-141).
RE_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
RE_HTML_IMG = re.compile(r"<img\s+[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
RE_MERMAID_FENCE = re.compile(r"```mermaid\b", re.IGNORECASE)
RE_BADGE_HOST = re.compile(
    r"img\.shields\.io|badge\.fury\.io|codecov\.io/.*badge\.svg|readthedocs\.org.*/badge",
    re.IGNORECASE,
)

# Architecture content (PS-142) — wider net than PS-141.
RE_TREE_CHARS = re.compile(r"[├└│]")
RE_FENCED_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)

RE_DETAILS_OPEN = re.compile(r"<details\b", re.IGNORECASE)
RE_DETAILS_CLOSE = re.compile(r"</details\s*>", re.IGNORECASE)
# Pipe-table detection (≥2 contiguous lines starting with `|`).
RE_PIPE_TABLE = re.compile(r"^\|[^\n]*\n\|[\s\-:|]+\|", re.MULTILINE)

# Canonical badge block markers.
RE_BADGES_BLOCK = re.compile(
    r"<!--\s*scitex-badges:start\s*-->(.*?)<!--\s*scitex-badges:end\s*-->",
    re.DOTALL | re.IGNORECASE,
)


# --- helpers ---------------------------------------------------------------


def section_body(text: str, name: str) -> tuple[str, int, int] | None:
    """Return (body_text, start_idx, end_idx) of `## <name>` section, or None.

    The body runs from end-of-header-line to the next H2 header (or EOF).
    """
    pat = SECTION_PATTERNS.get(name)
    if pat is None:
        return None
    m = pat.search(text)
    if not m:
        return None
    body_start = text.find("\n", m.end())
    body_start = body_start + 1 if body_start != -1 else m.end()
    next_h2 = re.search(r"^##\s+\S", text[body_start:], re.MULTILINE)
    body_end = body_start + next_h2.start() if next_h2 else len(text)
    return text[body_start:body_end], m.start(), body_end


def has_visual_content(body: str) -> bool:
    """PS-141 acceptance: at least one image / mermaid / non-badge <img>."""
    if RE_MD_IMAGE.search(body):
        return True
    if RE_MERMAID_FENCE.search(body):
        return True
    for m in RE_HTML_IMG.finditer(body):
        src = m.group(1)
        if not RE_BADGE_HOST.search(src):
            return True
    return False


def has_architecture_content(body: str) -> bool:
    """PS-142 acceptance: mermaid / file tree / ≥10-line fenced block / <img>."""
    if RE_MERMAID_FENCE.search(body):
        return True
    if RE_TREE_CHARS.search(body):
        return True
    for m in RE_FENCED_BLOCK.finditer(body):
        block = m.group(2)
        if block.count("\n") >= 10:
            return True
    if RE_HTML_IMG.search(body) or RE_MD_IMAGE.search(body):
        return True
    return False


def strip_details_spans(text: str) -> str:
    """Return `text` with every `<details>...</details>` span removed."""
    stripped = text
    while True:
        m_open = RE_DETAILS_OPEN.search(stripped)
        if not m_open:
            break
        m_close = RE_DETAILS_CLOSE.search(stripped, m_open.end())
        if not m_close:
            stripped = stripped[: m_open.start()]
            break
        stripped = stripped[: m_open.start()] + stripped[m_close.end() :]
    return stripped


def strip_badges_block(text: str) -> str:
    """Return `text` with the `<!-- scitex-badges:start/end -->` span removed."""
    return RE_BADGES_BLOCK.sub("", text)
