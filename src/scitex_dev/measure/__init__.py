#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/measure/__init__.py
"""Primitives for reading a fact out of text without lying about it.

The rule this package exists for: AN UNMATCHED READ IS AN UNANSWERED
QUESTION, not an empty answer -- and a read that matched the wrong instance
is worse than one that matched nothing, because it is confident.

Placement (2026-08-15): scitex-dev, not scitex-agent-container. The fleet
convention is PRIMITIVE IN scitex-dev, SPECIFICS DECLARED BY EACH LEAF, and
this is a primitive -- true for every package regardless of what it matches.
sac is the shared layer for AGENTS (lifecycle, specs, channels); a string
matcher living there would force every non-agent package to take the agent
runtime to get one, which is the too-broad box the constitution's vendor-name
rule warns about. (Argument: scitex-agent-container. scitex-hpc argued for
"shared tooling" on the grounds that a helper only one package can import gets
reimplemented badly four times -- which is the same requirement, and scitex-dev
is already the ecosystem's shared dev-tooling dependency, so it is satisfied.)
"""

from __future__ import annotations

from ._require_match import NoMatch, require_group, require_match

__all__ = ["NoMatch", "require_group", "require_match"]

# EOF
