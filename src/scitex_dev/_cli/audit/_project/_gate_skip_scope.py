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

A LINT RULE MUST NEVER MAKE THE CLEAREST CORRECT FORM THE EXPENSIVE ONE
------------------------------------------------------------------------
Formulated by scitex-hpc after this check's first inversion flagged their
fixed gate:

    root = module_name.split(".")[0]
    pytest.importorskip(root)
    importlib.import_module(module_name)

Two statements ON PURPOSE — the intermediate binding is what makes the
root/full-path distinction visible to a reader, which is the entire point of
the fix. Had the rule shipped flagging that, the author would have inlined it
and the file would have become harder to read to satisfy a checker that was
wrong. That is a rule making the codebase worse in order to make itself
quieter.

Its sibling, same author: a rule that flags documentation ABOUT a defect
teaches people to stop documenting the defect. Both are cases where the
checker's incentive and the reader's interest diverge, and the checker wins
because it is the thing that blocks the merge. Hence the two guarding tests
here — the readable two-line form, and prose describing the hazard — neither
of which is about detection accuracy at all.

The false positive was caught on the one repo whose owner was paying
attention. That is luck rather than design, and it is the argument for the
pilot ordering itself: run a new fleet rule against a repo whose owner will
notice and object, before the seventeen who will not.
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
    """One ``importorskip`` call that is NOT provably scoped to the root.

    THREE-VALUED, and the third value is the whole point. An earlier version
    of this module asked "can I prove this is a full-path skip?" and stayed
    SILENT otherwise. That is the permissive pole, sitting inside the fix for
    a permissive-pole bug — and it was not hypothetical:

        scitex-logging      name = module_name; importorskip(name)
        figrecipe           name = module_name; importorskip(name)
        scitex-notification importorskip(target)

    All three were reported CLEAN while skipping on the full path, because
    the argument was a local alias rather than the parametrize variable.
    Predicted by scitex-hpc under review ("unresolvable is not root, the same
    way unparseable is not optional") and measured on the same three files
    minutes later.

    So the question is inverted: not "can I prove this is bad?" but "can I
    prove this is SAFE?". Anything not provably root is reported, and
    `determined` says which kind of report it is.
    """

    line: int
    #: What was passed — a dotted literal, the parametrize variable, or the
    #: expression this check could not interpret.
    argument: str
    #: True  -> provably the full path (dotted literal, or the parametrize var)
    #: False -> could not be interpreted. Reported anyway, and reported AS
    #:          uninterpretable, because a rule that cannot classify must say
    #:          so rather than pass. Noisy and honest beats quiet and wrong.
    determined: bool = True


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


def _is_provably_root(arg: ast.expr) -> bool:
    """Can this argument be PROVEN to name a root package?

    Only two shapes qualify, and both are checked structurally rather than by
    spelling:

        "django"                     a literal with no dot
        <anything>.split(".")[0]     the canonical root-scoping idiom

    Everything else — including a bare local name that probably holds a root
    — returns False and gets reported. "Probably" is not a proof, and the
    cost asymmetry is stark: a false report costs one reviewer one minute; a
    false silence costs a gate that cannot fail, indefinitely.
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return "." not in arg.value

    if isinstance(arg, ast.Subscript):
        called = arg.value
        index = arg.slice
        if (
            isinstance(called, ast.Call)
            and getattr(called.func, "attr", None) == "split"
            and called.args
            and isinstance(called.args[0], ast.Constant)
            and called.args[0].value == "."
            and isinstance(index, ast.Constant)
            and index.value == 0
        ):
            return True

    return False


def _describe(arg: ast.expr) -> str:
    """A short rendering of the argument, for the finding text."""
    if isinstance(arg, ast.Constant):
        return repr(arg.value)
    if isinstance(arg, ast.Name):
        return arg.id
    try:
        return ast.unparse(arg)
    except Exception:  # stx-allow: fallback (reason: unparse is best-effort)
        return type(arg).__name__


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

    for scope, calls in _skip_calls_by_scope(tree):
        # Names bound to a provably-root expression IN THIS SCOPE. Without
        # this, the canonical readable form of the fix is reported:
        #
        #     root = module_name.split(".")[0]
        #     pytest.importorskip(root)
        #
        # which is scitex-hpc's fixed gate, verbatim. Flagging the clearest
        # spelling of the correct answer would push people toward the
        # one-liner to satisfy the checker — a rule shaping code away from
        # readability is a rule doing harm.
        #
        # Bindings are collected PER SCOPE rather than module-wide: a
        # module-wide map would let a `root = x.split(".")[0]` in one test
        # silence a genuinely unsafe `importorskip(root)` in another, which
        # is the false NEGATIVE this module was just rewritten to eliminate.
        rooted = {
            target.id
            for node in ast.walk(scope)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name) and _is_provably_root(node.value)
        }
        found.extend(_classify(calls, parametrized, rooted))

    return tuple(found)


def _skip_calls_by_scope(tree: ast.AST):
    """Yield (scope_node, importorskip_calls) for each function and module.

    Scoping matters for the `rooted` map above; see the comment there.
    """
    scopes = [tree] + [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    seen: set[int] = set()
    for scope in scopes:
        calls = []
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) != "importorskip":
                continue
            if not node.args or id(node) in seen:
                continue
            # Attribute the call to its INNERMOST enclosing function, so the
            # module-level pass does not re-report what a function already
            # handled with its own bindings.
            if scope is tree and _enclosing_function(tree, node) is not None:
                continue
            seen.add(id(node))
            calls.append(node)
        if calls:
            yield scope, calls


def _enclosing_function(tree: ast.AST, target: ast.Call):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if inner is target:
                    return node
    return None


def _classify(calls, parametrized: set[str], rooted: set[str]):
    for node in calls:
        arg = node.args[0]

        # Skipping on "django", on `name.split(".")[0]`, or on a name bound in
        # THIS scope to such an expression is the legitimate absent-peer case.
        # Everything else is reported.
        if _is_provably_root(arg):
            continue
        if isinstance(arg, ast.Name) and arg.id in rooted:
            continue

        # DETERMINED when the argument is demonstrably the full path: a dotted
        # literal, or a name bound by parametrize (which carries whatever
        # CROSS_PACKAGE_IMPORTS holds). Otherwise the call is still reported,
        # but AS uninterpretable — the shapes that land here are real, not
        # theoretical: a local alias (`name = module_name`), a fixture param
        # with no decorator to read, a loop target, a helper indirection.
        determined = (
            isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ) or (isinstance(arg, ast.Name) and arg.id in parametrized)

        yield FullPathSkip(node.lineno, _describe(arg), determined)


# EOF
