#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic short-label derivation for the icon generator."""

from __future__ import annotations

import re

_WORD_SPLIT_RE = re.compile(r"[\s_\-./]+")


def derive_label(name: str, *, max_chars: int = 3) -> str:
    """Derive a short uppercase label from ``name``.

    Deliberately simple scheme (operator: "don't overthink this")::

        split ``name`` on whitespace / ``-`` / ``_`` / ``.`` / ``/``
        1 word   -> first ``max_chars`` characters, uppercased
        2+ words -> first letter of up to ``max_chars`` words, uppercased

    Pure and deterministic -- same ``(name, max_chars)`` always yields
    the same label; no randomness, no external state.

    Callers wanting a different scheme (e.g. an operator-configured
    override) should pass ``label=...`` directly to
    :func:`scitex_dev._icons.generate_svg` /
    :func:`scitex_dev._icons.generate_png` instead of calling this
    function -- it is the *default* deriver, not the only allowed one.
    """
    words = [w for w in _WORD_SPLIT_RE.split(name.strip()) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:max_chars].upper()
    return "".join(w[0] for w in words[:max_chars]).upper()


# Bold uppercase sans-serif averages ~0.62x font-size per character width
# (measured against DejaVu Sans Bold / the common Linux CI/PIL default and
# generic sans-serif SVG rendering -- close enough across renderers since
# this only sets an upper bound, never an exact fit).
_AVG_CHAR_WIDTH_RATIO = 0.62
# Fraction of the canvas width the label may occupy, leaving margin.
_TARGET_WIDTH_FRACTION = 0.86
# Hard cap so a 1-2 char label doesn't render comically large.
_MAX_FONT_SIZE_FRACTION = 0.42


def label_font_size(label: str, size: int) -> float:
    """Derive a label font size that scales smoothly with ``label`` length.

    Callers previously used a two-step function (``0.42*size`` for <=3
    chars, a flat ``0.30*size`` for everything longer) that (a) jumped
    discontinuously at the 3/4-character boundary and (b) gave every
    label longer than 3 characters the SAME size regardless of whether
    it was 4 characters ("TODO") or 6 ("WRITER") -- visually
    inconsistent across a set of icons with varying label lengths (the
    actual bug report: icons looked mismatched in size/weight side by
    side in a Telegram avatar list).

    This targets a fixed on-canvas text width instead, so font size
    shrinks continuously as the label gets longer, capped so short
    labels never exceed the previous best-case size.
    """
    if not label:
        return size * _MAX_FONT_SIZE_FRACTION
    fit_size = (size * _TARGET_WIDTH_FRACTION) / (
        len(label) * _AVG_CHAR_WIDTH_RATIO
    )
    return min(size * _MAX_FONT_SIZE_FRACTION, fit_size)
