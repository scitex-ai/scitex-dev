#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compat shim — re-exports from `scitex_dev._dispatch`.

The reusable docs/skills CLI mixins moved to `scitex_dev._dispatch`
in 0.11.0. This shim keeps `from scitex_dev.cli import ...` working for
downstream packages (figrecipe, scitex-io, scitex-app, etc.) until they
migrate. Will be removed in 0.12.0.

Also the public promotion target for `attach_shell_completion` (previously
only reachable via the private `scitex_dev._cli._completion` path — see
`docs/adr/0003-ecosystem-boundary-ports-and-producers.md`). Resolved
lazily via `__getattr__` (PEP 562) rather than a top-level import: eagerly
importing `scitex_dev._cli` triggers `_cli/_root.py`'s module-level
registration of the ENTIRE subcommand tree (several hundred ms) as a
side effect, which every other symbol in this lightweight shim module
deliberately avoids paying.
"""

from __future__ import annotations

from ._core.dispatch import (
    docs_click_group,
    register_docs_subcommand,
    register_skills_subcommand,
    skills_click_group,
)

_COMPLETION_EXPORTS = (
    "attach_shell_completion",
    "completion_dropin_path",
    "generate_completion_script",
    "install_completion",
    "legacy_rc_lines",
)

__all__ = [
    *_COMPLETION_EXPORTS,
    "docs_click_group",
    "register_docs_subcommand",
    "register_skills_subcommand",
    "skills_click_group",
]


def __getattr__(name: str):
    if name in _COMPLETION_EXPORTS:
        from ._cli import _completion

        return getattr(_completion, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
