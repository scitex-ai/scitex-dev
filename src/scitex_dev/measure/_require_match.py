#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/measure/_require_match.py
"""Extract a fact from text, or FAIL AT THE POINT OF MEASUREMENT.

Built 2026-08-15 after three agents independently spent a night on one failure:
an instrument returns OUTPUT, and the output is not an ANSWER. The wrongness
then surfaces two or three steps downstream, where it is expensive and looks
like a different bug.

Collected instances, all measured that night, none of which announced itself:

  ZERO-MATCH READ AS A NEGATIVE
    `gh api`'s 404 BODY printed to stdout, defeating an emptiness test -- 76
    repositories recorded as having a variable when 8 had none.
    `command -v auditctl` under a PATH without /sbin: an installed binary read
    as absent, which hid a causal chain for hours.
    A `head -8` that cut the one source line disproving a finding.
    A regex `[^i]*` that could not cross the "i" in "warnings", matching
    nothing and reporting four blank verdicts.
    An empty grep read as "no hazard"; a fallback bound to `head`, which exits
    0 on empty input, so the fallback never fired.

  WRONG-INSTANCE MATCH -- THE HARDER CLASS
    `tail -1` of a log's engine-init lines returned the PREVIOUS generation's
    config. Nothing was empty, nothing errored, the line was real and
    correctly parsed -- and belonged to a different moment. It nearly produced
    a filed finding that was the exact opposite of the truth.
    `pgrep -f` matching the caller's OWN harness, so a guard concluded
    "already running" and skipped a launch: a check that does nothing and
    reports success.

THE DESIGN FOLLOWS FROM THOSE TWO CLASSES, and it is deliberately opinionated:

1. NO MATCH IS AN ERROR, never an empty string. That is the whole first class.
2. MULTIPLE MATCHES WITHOUT A DISAMBIGUATOR IS ALSO AN ERROR. This is the
   second class, and it is the part a naive "raise on empty" helper misses.
   `tail -1` and `head -1` are not selections -- they are guesses about
   ordering, and a log with two generations in it answers both of them
   confidently and wrongly. If several lines match, the caller must say WHICH
   ONE by narrowing, not by position.
3. `identity` is how you narrow: a second pattern the match must ALSO satisfy
   -- today's date, a run id, a pid. scitex-hpc's actual fix for the engine-init
   case was "an init line carrying today's date", and that is exactly this
   parameter.

WHAT THIS DELIBERATELY DOES NOT CATCH, so nobody trusts it further than it
goes: a TRUE answer to a question you did not realise you were asking. Measured
the same night -- reasoning output of 6797 chars at cap 2048, 13830 at 4096,
26449 at 8192, read as "expands to fill any budget" when 3.3 chars-per-token at
every cap is the signature of TRUNCATION. The measurement was real, correctly
taken, correctly parsed. Only asking "what ELSE would produce these same
numbers?" separates the two stories, and no helper can ask that for you.
"""

from __future__ import annotations

import re
from typing import Final

#: How much of the searched text to show when raising. Enough to recognise
#: what was actually searched -- the commonest surprise is that it was not the
#: text you thought.
_EXCERPT_CHARS: Final[int] = 300


class NoMatch(Exception):
    """Raised when a required extraction did not produce exactly one answer.

    Carries what was sought, what was searched, and why it failed -- because
    an error that only says "no match" sends the reader to the pattern, and
    the answer is usually in the text.
    """


def _excerpt(text: str) -> str:
    body = text[:_EXCERPT_CHARS]
    return body + ("..." if len(text) > _EXCERPT_CHARS else "")


def require_match(
    text: str,
    pattern: str,
    *,
    what: str,
    identity: str | None = None,
    flags: int = 0,
) -> re.Match[str]:
    """Return THE match for ``pattern`` in ``text``, or raise :class:`NoMatch`.

    Parameters
    ----------
    text
        What was actually searched. Shown in the error, because "I searched
        the wrong thing" is a more common failure than "my pattern is wrong".
    pattern
        The regex to find.
    what
        A human name for the fact being extracted ("the pytest summary", "the
        listening port"). It appears in the error, so the reader learns what
        was being looked for rather than only that something was not found.
    identity
        An optional SECOND regex the matched text must also satisfy. Use it
        when several lines can match and only one is the right INSTANCE --
        a date, a run id, a pid. This is the wrong-generation guard.
    flags
        Passed to :func:`re.finditer`.

    Raises
    ------
    NoMatch
        If nothing matched; if several matched and no ``identity`` narrowed it
        to one; or if ``identity`` was given and nothing satisfied it.
    """
    candidates = list(re.finditer(pattern, text, flags))
    if not candidates:
        raise NoMatch(
            f"{what}: pattern {pattern!r} matched NOTHING. This is an error, "
            f"not an empty result -- an unmatched read is an unanswered "
            f"question. Searched {len(text)} char(s): {_excerpt(text)!r}"
        )

    if identity is not None:
        narrowed = [m for m in candidates if re.search(identity, m.group(0), flags)]
        if not narrowed:
            raise NoMatch(
                f"{what}: {len(candidates)} line(s) matched {pattern!r} but "
                f"NONE satisfied identity {identity!r}. The instrument found "
                f"something real and it was the wrong instance -- a different "
                f"run, generation, or process. Candidates: "
                f"{[m.group(0)[:80] for m in candidates[:3]]}"
            )
        candidates = narrowed

    if len(candidates) > 1:
        raise NoMatch(
            f"{what}: {len(candidates)} matches for {pattern!r}, and no "
            f"`identity` to choose between them. Refusing to pick by "
            f"POSITION: `tail -1`/`head -1` are guesses about ordering, and a "
            f"log holding two generations answers both confidently and "
            f"wrongly. Narrow the pattern or pass identity=. First three: "
            f"{[m.group(0)[:80] for m in candidates[:3]]}"
        )

    return candidates[0]


def require_group(
    text: str,
    pattern: str,
    *,
    what: str,
    group: int | str = 1,
    identity: str | None = None,
    flags: int = 0,
) -> str:
    """:func:`require_match`, returning one capture group's text.

    The common case is wanting the captured value, not the match object, and
    a helper people find fiddly gets bypassed -- which returns them to
    `tail -1`.
    """
    return require_match(
        text, pattern, what=what, identity=identity, flags=flags
    ).group(group)


__all__ = ["NoMatch", "require_group", "require_match"]

# EOF
