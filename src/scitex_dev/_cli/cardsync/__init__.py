#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cardsync …`` — measure drift between fleet card stores.

Three hosts each hold a full copy of the card store, and nothing reconciles
them. On 2026-08-10 they had drifted to 2,341 differing rows, which was
closed by hand — and the drift was only noticed because a handoff between
two agents silently failed to arrive.

This group is the periodic look. READ-ONLY by construction: it reports what
differs and writes nothing. See :mod:`scitex_dev.cardsync` for why the write
half lives in scitex-cards rather than here.

Verbs:
  * ``report`` — compare two stores and print the verdict counts.
"""

from __future__ import annotations

from ._cmd import parse_endpoint, register_cardsync_commands

__all__ = ["parse_endpoint", "register_cardsync_commands"]

# EOF
