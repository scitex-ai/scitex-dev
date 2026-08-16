#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/audit/_project/_gate_skip_scope.py

"""Does a cross-package gate skip on the FULL path, or only on the ROOT?

WHY THIS EXISTS, measured 2026-08-16 across every readable checkout:

    gates carrying importorskip : 19
    gates found                 : 19

All of them, scitex-dev's own included, call
``pytest.importorskip(module_name)`` on the FULL dotted path. That skips on
any ``ImportError``, and a renamed submodule raises ``ModuleNotFoundError``
(an ``ImportError`` subclass). So the rename SKIPS, control never reaches the
hard import on the next line, and the gate reports GREEN.

The deployed docstring states the intended behaviour:

    installed AND imports        -> PASSES
    installed BUT import fails   -> "test FAILS loudly"      <- does not hold
    NOT installed                -> SKIPPED via importorskip

The middle line is the only reason the gate exists. Proven with both arms in
one run: ``importorskip("pkg._gone")`` -> SKIPPED;
``importorskip("pkg")`` then ``import_module("pkg._gone")`` -> FAILED.

WHY THIS IS A SEPARATE CHECK RATHER THAN A FIX
-----------------------------------------------
``install-cross-package-gate`` preserves everything below the closing
sentinel BYTE-IDENTICALLY, and the broken assertion lives in that preserved
tail. So regenerating all 19 gates fixes ZERO of them. The sweep is the
automatable half and it is not the half that matters; only a finding gets the
19 owners to change the assertion.

WHY IT DOES NOT SIMPLY BAN ``importorskip``
--------------------------------------------
Because that would be the opposite pole of the same bug. Root-presence does
NOT imply submodule-presence, and two real cases prove it: scitex-dev's linter
plugins are a SEPARATE DISTRIBUTION, and ``scitex_hpc._mcp`` requires the
optional ``fastmcp`` extra (7 tests skip without it, all 7 pass with ``[all]``).
Banning the skip outright would convert a legitimate absence into a hard
failure — a gate that cannot PASS, in place of one that cannot FAIL.

So the rule is narrow and it is about SCOPE, not about the function: skipping
on the ROOT is legitimate; skipping on the FULL dotted path is what hides the
rename.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = [
    "FullPathSkip",
    "find_full_path_skips",
]


@dataclass(frozen=True)
class FullPathSkip:
    """One ``importorskip`` call whose scope is the full dotted path."""

    line: int
    #: What was passed — a literal like ``"scitex_io._cache"``, or the name of
    #: the parametrize variable (``module_name``) when the call skips on
    #: whatever the parametrization supplies, which is the full path.
    argument: str


def _parametrize_names(tree: ast.AST) -> set[str]:
    """Variables bound by ``@pytest.mark.parametrize`` in this module.

    A call skipping on one of these skips on the FULL path, because that is
    what ``CROSS_PACKAGE_IMPORTS`` holds. Resolving this from the decorator
    rather than hard-coding ``module_name`` matters: the deployed gates do not
    agree on the variable name, and a check that only knew one spelling would
    silently pass the others -- a check that cannot fail, added while fixing a
    gate that cannot fail.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = getattr(func, "attr", None)
        if attr != "parametrize" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.update(part.strip() for part in first.value.split(","))
    return {n for n in names if n}


def find_full_path_skips(source: str) -> tuple[FullPathSkip, ...]:
    """Locate ``importorskip`` calls that skip on a full dotted path.

    Returns an empty tuple both when the file is clean AND when it cannot be
    parsed. That is deliberate for THIS caller: PS-140 already reports an
    unparseable gate through its own path, and emitting a second finding for
    the same file would double-count. The distinction is not being collapsed
    silently -- it is being handled once, upstream.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()

    parametrized = _parametrize_names(tree)
    found: list[FullPathSkip] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "importorskip":
            continue
        if not node.args:
            continue
        arg = node.args[0]

        # A literal is only a problem when it names a SUBMODULE. Skipping on
        # "django" or "scitex_ssh" is the legitimate absent-peer case.
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if "." in arg.value:
                found.append(FullPathSkip(node.lineno, arg.value))
            continue

        # A parametrize variable carries whatever CROSS_PACKAGE_IMPORTS holds,
        # which is the full path.
        if isinstance(arg, ast.Name) and arg.id in parametrized:
            found.append(FullPathSkip(node.lineno, arg.id))

    return tuple(found)


# EOF
