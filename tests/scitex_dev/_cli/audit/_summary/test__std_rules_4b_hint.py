#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§4b's remediation names an import — so this suite RUNS that import.

Reported by scitex-ui 2026-08-15, confirmed here. The hint read:

    "help is free-form text — construct via CliHelp
     (scitex_dev.ecosystem.help_spec)"

and that path raises::

    ModuleNotFoundError: No module named 'scitex_dev.ecosystem.help_spec';
    'scitex_dev.ecosystem' is not a package

`scitex_dev.ecosystem` re-exports 22 names including `CliHelp`, but has no
`__path__`, so nothing is addressable beneath it.

WHY A TEST AND NOT A CAREFUL STRING. The previous hint was also written
carefully; what it lacked was anything that would notice when it stopped
being true. A remediation is a promise the reader will act on, and the only
way to keep that promise honest is to act on it here first.

WHAT IT COST, which is why this is not a cosmetic suite: scitex-ui copied the
hint onto a card on 2026-07-29, ran the import, read `ModuleNotFoundError` as
"help_spec is not public API yet", and deferred the migration for two weeks.
`CliHelp` had been public throughout, including in the 0.42.0 their container
runs. **A wrong name in a hint fails in the direction that makes the status
quo look correct — the one direction nobody re-checks.**
"""

from __future__ import annotations

import importlib
import re

import click
import pytest

from scitex_dev._cli.audit._summary._audit import Violation
from scitex_dev._cli.audit._summary._std_rules import check_spec_built_help

#: Dotted paths inside the hint text. Matches `a.b.c` and the module half of
#: `from a.b import X`, which is what a reader would actually type.
_DOTTED = re.compile(r"\b(scitex_dev(?:\.[A-Za-z_][A-Za-z0-9_]*)+)")


@pytest.fixture()
def the_4b_message() -> str:
    """The §4b remediation exactly as a reader sees it."""

    @click.command()
    def free_form():
        """Plain docstring help, no CliHelp spec."""

    out: list[Violation] = []
    check_spec_built_help(free_form, "demo free-form", out)
    return out[0].message


def test_the_rule_still_fires_on_free_form_help(the_4b_message: str) -> None:
    """The positive control.

    Every assertion below reads the message this fixture produced. If the
    rule stopped firing, the fixture would raise on `out[0]` — but a future
    refactor could make it emit an empty-but-present message and the import
    checks would then pass vacuously.
    """
    # Arrange
    message = the_4b_message
    # Act
    mentions_the_remedy = "CliHelp" in message
    # Assert
    assert mentions_the_remedy, f"§4b no longer names its remedy: {message!r}"


def test_the_hint_names_at_least_one_importable_path(the_4b_message: str) -> None:
    """A remediation with no import in it cannot be followed."""
    # Arrange
    message = the_4b_message
    # Act
    paths = _DOTTED.findall(message)
    # Assert
    assert paths, (
        "§4b's remediation names no `scitex_dev.*` path, so a reader is told "
        f"to 'construct via CliHelp' with nowhere to get it from: {message!r}"
    )


def test_every_path_the_hint_names_actually_imports(the_4b_message: str) -> None:
    """THE REGRESSION. `scitex_dev.ecosystem.help_spec` fails exactly here."""
    # Arrange
    paths = _DOTTED.findall(the_4b_message)
    # Act
    failures = []
    for path in paths:
        try:
            importlib.import_module(path)
        except ImportError as exc:
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
    # Assert
    assert not failures, (
        "§4b tells the reader to import something that does not import. That "
        "reads as 'not public yet' and stalls the migration it was meant to "
        "start:\n  " + "\n  ".join(failures)
    )


def test_the_symbol_the_hint_promises_is_reachable_from_the_public_module() -> None:
    """`CliHelp` must be importable the way the hint spells it.

    Separate from the path check because a package could import cleanly and
    still not export the name the reader was sent for.
    """
    # Arrange
    module = importlib.import_module("scitex_dev.ecosystem")
    # Act
    exported = getattr(module, "CliHelp", None)
    # Assert
    assert exported is not None, (
        "`scitex_dev.ecosystem` imports but does not export `CliHelp`, so the "
        "remediation is unfollowable even though its path resolves"
    )


def test_the_unimportable_predecessor_is_gone(the_4b_message: str) -> None:
    """Name the exact string that caused the two-week stall.

    Belt and braces over the generic check above: this one fails with the
    incident in the message, so whoever reintroduces it learns why rather
    than only that.
    """
    # Arrange
    message = the_4b_message
    # Act
    reintroduced = "scitex_dev.ecosystem.help_spec" in message
    # Assert
    assert not reintroduced, (
        "the hint again names `scitex_dev.ecosystem.help_spec`, which raises "
        "ModuleNotFoundError ('scitex_dev.ecosystem' is not a package). "
        "scitex-ui read that as 'help_spec is not public API yet' and "
        "deferred the work for two weeks. Use "
        "`from scitex_dev.ecosystem import CliHelp`."
    )


# EOF
