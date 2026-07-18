#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic SVG icon rendering.

Pure standard library (``xml.sax.saxutils.escape`` only) -- no
rasterization dependency, so importing this module (or the top-level
``scitex_dev._icons`` package) never requires Pillow.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from ._colors import resolve_color
from ._label import derive_label, label_font_size

DEFAULT_SIZE = 512
WORDMARK = "SciTeX"


def generate_svg(
    name: str,
    *,
    size: int = DEFAULT_SIZE,
    label: str | None = None,
    color: str | None = None,
    wordmark: str | None = WORDMARK,
) -> str:
    """Render a deterministic square SVG icon for ``name``.

    Style: solid brand-color full-bleed square background + a short
    white label centered in the upper portion + an optional small
    wordmark near the bottom -- the same visual spirit as the fleet's
    PIL-based bot-avatar script, reimplemented dependency-free as
    plain SVG markup.

    Args:
        name: input string (agent id / package name / arbitrary label).
            Drives both the derived label (via :func:`derive_label`) and
            the resolved color (via :func:`resolve_color`) unless
            overridden below.
        size: square canvas size in SVG user units (``viewBox``).
        label: explicit short label; overrides the name-derived one.
        color: explicit hex fill; overrides the resolved brand color.
        wordmark: small caption near the bottom; pass ``None`` to omit.

    Returns:
        A complete ``<svg>...</svg>`` document as a ``str``.

    Determinism: same ``(name, size, label, color, wordmark)`` in always
    produces byte-identical output -- no randomness, no wall-clock
    dependency, no environment-dependent font resolution (SVG text uses
    the CSS generic family ``sans-serif``, resolved by the *renderer*,
    not by this function).
    """
    resolved_label = (label if label is not None else derive_label(name)).upper()
    fill = color or resolve_color(name)
    label_size = label_font_size(resolved_label, size)
    label_y = size * 0.46
    wordmark_font_size = size * 0.11
    wordmark_y = size * 0.72

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">',
        f'<rect width="{size}" height="{size}" fill="{fill}"/>',
        f'<text x="{size / 2:.1f}" y="{label_y:.1f}" font-family="sans-serif" '
        f'font-size="{label_size:.1f}" font-weight="700" fill="#ffffff" '
        f'text-anchor="middle" dominant-baseline="middle">'
        f"{escape(resolved_label)}</text>",
    ]
    if wordmark:
        parts.append(
            f'<text x="{size / 2:.1f}" y="{wordmark_y:.1f}" font-family="sans-serif" '
            f'font-size="{wordmark_font_size:.1f}" fill="#ffffff" '
            f'text-anchor="middle" dominant-baseline="middle">'
            f"{escape(wordmark)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts) + "\n"
