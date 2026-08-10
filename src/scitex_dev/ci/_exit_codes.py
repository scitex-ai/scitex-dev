#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/ci/_exit_codes.py
"""Exit codes no CLI framework can impersonate.

This module is deliberately tiny and dependency-free so that a hook, a
release script, or anything else that only needs the vocabulary can import
it without pulling in ``subprocess`` and a GitHub decision tree.

WHY THESE NUMBERS, measured 2026-08-09 by walking into it
---------------------------------------------------------
``NOT_READY`` was **2**. The venv held a scitex-dev that predated the
``ci verify`` subcommand, so Click answered ``No such command 'verify'`` and
exited **2** — its usage code — and the calling hook read that as the domain
answer and reported *"the pull request is NOT ready to merge"* about a pull
request green on all seven checks.

A missing verb impersonated a verdict about the code.

The constitution forbids exactly this, in as many words (§2, "Answer in a
fixed, declared shape")::

    Never overload a small exit code with a domain meaning: 1 and 2 already
    mean "generic failure" and "usage error" in every CLI framework, so a
    missing or renamed verb will impersonate your success value.

The rule was written before the bug and did not prevent it. It was walked
past by someone who had read it, inside the very change that fixed two
sibling instances of the same defect — UNKNOWN collapsed into a pole:

    warn-tier notice   read as a violation
    could-not-measure  read as a failure
    cannot-answer      read as no

That is the argument for :func:`_assert_no_domain_code_is_framework_reserved`
being executable rather than prose. A rule that must be REMEMBERED is
forgotten exactly when it matters, and the person forgetting it here was the
one most primed to remember.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final, Iterable

__all__ = [
    "EXIT_NOT_READY",
    "EXIT_READY",
    "EXIT_UNKNOWN",
    "EXIT_USAGE",
    "FRAMEWORK_RESERVED_EXIT_CODES",
    "ExitCode",
    "assert_no_domain_code_is_framework_reserved",
]

#: Exit codes the FRAMEWORK has already claimed, before any of our code runs.
#: Click raises ``UsageError`` — exit **2** — for an unknown subcommand or a
#: bad option, and argparse does the same. 1 is the shell's generic failure.
#:
#: Declared as data so it can be CHECKED against, not merely read.
FRAMEWORK_RESERVED_EXIT_CODES: Final[frozenset[int]] = frozenset({1, 2})


class ExitCode(IntEnum):
    """The process-level answer. Three-valued, and none of it borrowed."""

    #: Every check that ran belongs to the current head and passed.
    READY = 0
    #: A definite no, with at least one reason naming a specific check.
    NOT_READY = 10
    #: The question could not be answered. NOT a synonym for NOT_READY —
    #: "no" and "I could not tell" call for different actions, and a caller
    #: that cannot distinguish them will eventually treat one as the other.
    CANNOT_DETERMINE = 11


def assert_no_domain_code_is_framework_reserved(codes: "Iterable" = ExitCode) -> None:
    """Fail at IMPORT if a domain code collides with a framework code.

    THE POINT IS THAT THIS IS NOT A COMMENT. The comment version already
    existed — in the constitution, quoted in the module docstring — and was
    walked past. This runs in every process that imports the module,
    including the subprocess a gating hook shells out to, so the collision
    cannot be reintroduced by an edit that looks locally reasonable.

    ``codes`` is a parameter rather than a hard reference to :class:`ExitCode`
    so that a test can hand it a REAL enum shaped like the bug, instead of
    reaching in and rewriting this module's globals. A guard verified by
    patching the thing it guards is not verified.
    """
    collisions = {
        member.name: member.value
        for member in codes
        if member.value in FRAMEWORK_RESERVED_EXIT_CODES
    }
    if collisions:
        raise RuntimeError(
            f"ExitCode collides with framework-reserved exit codes: {collisions}. "
            f"{sorted(FRAMEWORK_RESERVED_EXIT_CODES)} already mean 'generic "
            "failure' and 'usage error'. Click exits 2 for an unknown "
            "subcommand BEFORE this module runs, so a domain meaning parked "
            "there is indistinguishable from a typo or a stale install. On "
            "2026-08-09 that exact collision made a checker lacking the verb "
            "report a green pull request as NOT ready to merge. Pick a value "
            "outside that set."
        )


assert_no_domain_code_is_framework_reserved()


#: Back-compatible aliases. ``IntEnum`` members ARE ints, so comparisons and
#: ``SystemExit(code)`` keep working; only the numbers changed.
EXIT_READY: Final[int] = ExitCode.READY
EXIT_NOT_READY: Final[int] = ExitCode.NOT_READY
EXIT_UNKNOWN: Final[int] = ExitCode.CANNOT_DETERMINE

#: NOT ours. Named here only so a caller can RECOGNISE it.
#:
#: This was previously declared as ``1``, which was simply wrong — Click
#: exits **2** on a usage error. Declaring the wrong number for someone
#: else's code is precisely how we came to believe 2 was free to take.
EXIT_USAGE: Final[int] = 2


# EOF
