#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ecosystem/_cmds/_gate_sentinel.py

"""Preserve hand-written content when a generated gate is regenerated.

WHY THIS EXISTS, measured rather than assumed. Cross-package gates deployed
across the fleet on 2026-07-29 carry a sentinel pair and a docstring telling
the reader to "add hand-written cases below the second sentinel". The tool
that wrote them was a one-shot script since deleted, so nothing regenerates
them today and the invitation looked harmless.

IT WAS NOT HARMLESS: THE INVITATION WAS ACCEPTED. scitex-hpc swept 20
checkouts on 2026-08-16 and found, below the closing sentinel:

    scitex-dev       60 lines   a test AND a documented prose block on
                                compat-ALIAS shims and __name__ truthfulness
    scitex-logging   17 lines   a second hand-written test
    scitex-io        10 lines   the GENERATED test, deliberately strengthened
                                (`mod.__name__ == module_name` in place of
                                 `mod is not None`)
    others            8-9       template only

So a regenerator that treats the whole file as its own would destroy work in
at least two repositories and silently revert a deliberate strengthening in a
third. "At least" is load-bearing: that scan covered working checkouts on ONE
host and compared line counts, not semantics, so it is a LOWER BOUND.

PRESERVATION BOUNDARIES:

1. Everything after the closing sentinel is preserved BYTE-IDENTICALLY. Not
   "the tests found there" -- scitex-dev's tail is partly prose, and a
   tests-aware preserver would drop exactly that.
2. A file that cannot be parsed for a sentinel is REFUSED, never silently
   overwritten. Unparseable is not empty.
3. Imports before the opening sentinel are preserved as exact AST source
   segments. Other header statements are refused rather than discarded.
   The generated header prose and comments are regenerated.
"""

from __future__ import annotations

import io
import tokenize
from dataclasses import dataclass

from ._gate_header import read_header_imports

__all__ = [
    "BEGIN_SENTINEL",
    "END_SENTINEL",
    "SplitGate",
    "split_at_sentinel",
]

#: The markers the 2026-07-29 population carries. Matched EXACTLY: a fuzzy
#: match risks splitting on a line that merely discusses the sentinel, and
#: this module's whole job is to not guess about where user content starts.
BEGIN_SENTINEL = "# ===== AUTO-GENERATED: cross-package imports ====="
END_SENTINEL = "# ===== END AUTO-GENERATED ====="


@dataclass(frozen=True)
class SplitGate:
    """The result of looking for preservable content in an existing gate.

    THREE-VALUED, per constitution §2, because "no tail" and "cannot tell"
    call for different actions and collapsing them is how a regenerator
    silently eats a file:

        has_sentinel=True   -> `tail` is user content; preserve it verbatim
        has_sentinel=False  -> no marker; there is nothing to preserve, and
                               the caller decides whether overwriting is OK
        readable=False      -> the file exists but could not be read; the
                               caller must REFUSE, because an unreadable
                               file is not an absent one
    """

    readable: bool
    has_sentinel: bool
    tail: str
    header_imports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.readable and (
            self.has_sentinel or self.tail or self.header_imports
        ):
            raise ValueError(
                "SplitGate(readable=False) cannot carry a sentinel or a tail: "
                "nothing was read, so any content here would be invented."
            )


def split_at_sentinel(existing: str | None) -> SplitGate:
    """Read a unique marker pair, supported header imports and untouched tail.

    `existing` is the file's current text, or None when it does not exist.
    The returned `tail` includes the closing sentinel line itself, so a
    caller can concatenate a freshly rendered head with it and get a file
    whose user section is unchanged to the byte.
    """
    if existing is None:
        return SplitGate(readable=True, has_sentinel=False, tail="")

    try:
        tokens = tokenize.generate_tokens(io.StringIO(existing).readline)
        markers = [
            token
            for token in tokens
            if token.type == tokenize.COMMENT
            and token.string in (BEGIN_SENTINEL, END_SENTINEL)
        ]
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError("Cannot locate markers in an unparseable gate") from exc
    if not markers:
        return SplitGate(readable=True, has_sentinel=False, tail="")
    if [token.string for token in markers] != [BEGIN_SENTINEL, END_SENTINEL] or any(
        token.start[1] != 0 for token in markers
    ):
        raise ValueError(
            "Gate requires one unambiguous, ordered column-zero sentinel pair"
        )
    lines = existing.splitlines(keepends=True)
    begin = sum(map(len, lines[: markers[0].start[0] - 1]))
    end = sum(map(len, lines[: markers[1].start[0] - 1]))
    imports = read_header_imports(existing[:begin])
    return SplitGate(
        readable=True, has_sentinel=True, tail=existing[end:], header_imports=imports
    )


# EOF
