#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scitex-dev home-area management: the ``~/.scitex`` lifecycle contract.

Every scitex package keeps per-user state under ``~/.scitex/<pkg>/``. This
package owns the small shared primitives that keep that tree healthy so no
leaf has to re-implement them.
"""

from __future__ import annotations

from ._managed_by_git import DOTSCITEX_DIRNAME, ensure_dotscitex_managed_by_git

__all__ = [
    "DOTSCITEX_DIRNAME",
    "ensure_dotscitex_managed_by_git",
]
