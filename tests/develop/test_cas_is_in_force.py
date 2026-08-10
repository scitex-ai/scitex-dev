#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The CAS escape hatch must stay unused in production code.

`Store.put` takes `expected_revision` as a REQUIRED argument, three-valued:
`NEW_RECORD`, an `int`, or `ANY_REVISION`. The first two are real
compare-and-set. The third is the opt-out — it writes whatever the current
revision is.

Measured 2026-08-10: `ANY_REVISION` has ZERO production call sites. That is
the correct state, and nothing enforced it. `store/README.md` tells a reader
to run `rg ANY_REVISION` to audit it, which makes the guarantee depend on
somebody remembering to look.

That matters more than an ordinary style rule, because of what CAS is load
bearing for. ADR-0006 Decision 7 opens TCP 55432 to external clients, and its
sequencing constraint is explicit: concurrency control today is an
`fcntl.flock` on a host-local file, a remote writer holds no descriptor on
this host, so compare-and-set inside the database is a PRECONDITION of
opening the port. If callers drift to `ANY_REVISION`, that precondition is
silently withdrawn while every signature still says `expected_revision`.

A gate that cannot fail is not a gate. This test is the gate.

WHY AST AND NOT `rg`
--------------------
A text search for `ANY_REVISION` matches its definition, its re-export, the
`__all__` entry, the import lines, this docstring, and the README — six hits
before a single real use. Counting source text would report the hatch as
widely used and the rule as unenforceable.

Walking the AST for `ast.Name` nodes in ARGUMENT position answers the
question actually being asked: is anyone PASSING it? Imports, `__all__`
strings and prose are structurally different nodes and drop out for free,
with no exclusion list to maintain and no exclusion list to get wrong.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scitex_dev

_HATCH = "ANY_REVISION"
_SRC = Path(scitex_dev.__file__).parent


def _hatch_call_sites() -> list[str]:
    """Every place `ANY_REVISION` is PASSED as a call argument.

    Returns `file:line` strings. Positional args, keyword args and starred
    args all count — each one is a real write that skips the check.
    """
    sites: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            passed = [*node.args, *(kw.value for kw in node.keywords)]
            for arg in passed:
                inner = arg.value if isinstance(arg, ast.Starred) else arg
                if isinstance(inner, ast.Name) and inner.id == _HATCH:
                    sites.append(f"{path.relative_to(_SRC)}:{inner.lineno}")
    return sites


def test_the_cas_escape_hatch_has_no_production_call_sites():
    """No shipped code may write with the revision check opted out."""
    # Arrange
    hatch = _HATCH

    # Act
    sites = _hatch_call_sites()

    # Assert
    assert not sites, (
        f"{hatch} is passed at {len(sites)} call site(s): {sites}. "
        "Every one of these writes skips compare-and-set. ADR-0006 Decision 7 "
        "makes CAS a precondition of opening TCP 55432, because an "
        "fcntl.flock cannot serialize a remote writer. Pass NEW_RECORD or the "
        "revision you read. If a call genuinely cannot know the revision, "
        "that is a design question for the ADR, not a keyword argument."
    )


def test_the_detector_finds_a_hatch_call_when_one_exists():
    """The control: this test is worthless if the walker cannot see a use.

    Without this, the rule above passes just as happily against a walker that
    matches nothing at all — the same unearned green the rule exists to
    prevent.
    """
    # Arrange
    source = "store.put(record, expected_revision=ANY_REVISION)"

    # Act
    found = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name) and node.id == _HATCH
    ]

    # Assert
    assert found


def test_the_escape_hatch_is_still_exported():
    """It must remain reachable and named, not deleted.

    Deleting it would make this rule trivially true while removing the
    explicit, greppable way to say "I know what I am skipping" — turning a
    visible opt-out into an invisible one somewhere else.
    """
    # Arrange
    from scitex_dev import store

    # Act
    exported = getattr(store, _HATCH, None)

    # Assert
    assert exported is not None


def test_expected_revision_has_no_default():
    """`put` must force the caller to state an intent, not infer one."""
    # Arrange
    import inspect

    from scitex_dev.store import Store

    # Act
    param = inspect.signature(Store.put).parameters["expected_revision"]

    # Assert
    assert param.default is inspect.Parameter.empty


# EOF
