#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exception base for ``ci-template apply``.

Its own module purely to break a cycle: ``_gate`` raises the subclass
``BranchProtectionGateError`` and ``_apply`` imports ``_gate``, so the shared
base cannot live in either without one importing the other back.
"""

from __future__ import annotations


class ApplyError(RuntimeError):
    """Operator-facing apply failure (bad target, parse error, etc.)."""


# EOF
