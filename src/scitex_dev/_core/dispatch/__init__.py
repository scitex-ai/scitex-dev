#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable CLI mixins for ``docs`` and ``skills`` subcommands.

Each package adds subcommands with minimal boilerplate::

    # In scitex_writer/_cli/__init__.py (argparse)
    from scitex_dev.cli import register_docs_subcommand, register_skills_subcommand
    register_docs_subcommand(subparsers, package="scitex-writer")
    register_skills_subcommand(subparsers, package="scitex-writer")

    # Or with Click
    from scitex_dev.cli import docs_click_group
    cli.add_command(docs_click_group(package="scitex-writer"))

Split from the former flat ``dispatch.py`` module (2026-07-11,
CLI-standardization audit pass §4b) -- one flavor (argparse / Click) x
one subcommand family (docs / skills) per file, mirroring the
``_audit_per_target/`` and ``_branch_protection/`` package splits. This
``__init__.py`` is the thin orchestrator; every external import site
(``scitex_dev/cli.py``, ``scitex_dev/_cli/_root.py``) imports from
``scitex_dev._core.dispatch``, which a package's ``__init__.py``
satisfies identically to the former flat module.
"""

from __future__ import annotations

from ._docs_argparse import register_docs_subcommand
from ._docs_click import docs_click_group
from ._skills_argparse import register_skills_subcommand
from ._skills_click import skills_click_group

__all__ = [
    "register_docs_subcommand",
    "register_skills_subcommand",
    "docs_click_group",
    "skills_click_group",
]
