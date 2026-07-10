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
