#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic name -> brand color resolution for the icon generator.

Known ecosystem components get a curated brand color (ported as a
starting point from the one-off ``claude-code-telegrammer`` fleet
avatar script -- ``docs/icons/generate_bot_icons.py``, commit
``1973772`` in ``scitex-ai/claude-code-telegrammer`` -- consulted as
REFERENCE MATERIAL only; this module does not import from or depend on
that package). Any other name falls back to a deterministic
``hash(name) -> palette-index`` color: the same name always resolves to
the same color, with no randomness and no wall-clock dependency.
"""

from __future__ import annotations

import hashlib

# Known SciTeX ecosystem component -> brand hex color. Plain dict, not a
# migration-gated registry -- extend freely as new components need a
# curated (rather than hashed) color.
KNOWN_COLORS: dict[str, str] = {
    "cct": "#1a2a40",  # claude-code-telegrammer -- SciTeX-01 navy
    "writer": "#5865c9",  # scitex-writer -- indigo
    "figrecipe": "#d97742",  # figrecipe -- orange
    "dsp": "#6c8ba0",  # scitex-dsp -- SciTeX-04 steel
    "scitex-dev": "#2f7a4f",  # scitex-dev -- green
    "sac": "#7a4fd9",  # scitex-agent-container -- purple
    "todo": "#2f9e9e",  # scitex-todo -- teal
}

# Deterministic fallback palette for names not in KNOWN_COLORS. The
# ORDER IS PART OF THE DETERMINISM CONTRACT: reordering, inserting, or
# removing an entry silently changes every already-issued unmapped-name
# color. Only ever append new colors at the end.
_FALLBACK_PALETTE: tuple[str, ...] = (
    "#c0392b",
    "#8e44ad",
    "#2980b9",
    "#16a085",
    "#d35400",
    "#2c3e50",
    "#27ae60",
    "#e67e22",
    "#2c6ea6",
    "#8d6e63",
    "#546e7a",
    "#00695c",
)


def resolve_color(name: str) -> str:
    """Return a deterministic hex color for ``name``.

    Known ecosystem names (see ``KNOWN_COLORS``, matched case-insensitively
    after stripping whitespace) return their curated brand color. Any
    other string is hashed with SHA-256 (stable across processes and
    Python versions, unlike the salted builtin ``hash()``) into an index
    over ``_FALLBACK_PALETTE``.
    """
    key = name.strip().lower()
    if key in KNOWN_COLORS:
        return KNOWN_COLORS[key]
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    index = digest[0] % len(_FALLBACK_PALETTE)
    return _FALLBACK_PALETTE[index]
