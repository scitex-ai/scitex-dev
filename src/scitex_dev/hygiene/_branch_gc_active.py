#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The ACTIVE-WORK signal — the leg no existing branch tool has.

The 2026-08-08 incident did not happen because a branch looked merged or
looked old. It happened because the branches were the SUBSTRATE of an
in-flight operator mission, and nothing in the deleting tool could see
that. Ancestry, age and PR state are all properties of the branch. This
leg is the only one that asks a question about the FLEET.

The signal is the shared card store, read through scitex-cards' own verbs
(optional import — this package never hard-depends on it). Every
NON-TERMINAL card contributes tokens, and a branch whose name overlaps a
token is KEPT.

``None`` IS NOT AN EMPTY SET. If the store cannot be resolved, the package
is absent, or the read fails, this returns ``None`` and the engine ABORTS
THE WHOLE PASS with zero deletions. Not "keep a few extra" — abort. If you
cannot see what the fleet is working on, you cannot know what is
substrate, and a sweep that proceeds anyway is exactly the sweep that ran
that night.
"""

from __future__ import annotations

from typing import Callable

__all__ = [
    "ActiveRefs",
    "MIN_TOKEN_LENGTH",
    "branch_is_active",
    "card_active_tokens",
    "is_slug_shaped",
]

#: () -> the branch/slug tokens the fleet is working on, or None when the
#: signal is UNAVAILABLE.
ActiveRefs = Callable[[], "set[str] | None"]

#: Tokens shorter than this are dropped.
#:
#: MEASURED, and the reason this is 8 and not 4. Against the real
#: scitex-agent-container checkout (59 local branches) a 4-character
#: threshold with no shape requirement matched ALL 59 — the prose word
#: "feat" in some card's note is a substring of every ``feat/*`` branch.
#: A leg that keeps everything is not conservative, it is BROKEN: it
#: reports the same verdict regardless of input, so it can neither protect
#: the branch it should nor be trusted when it says a branch is free.
MIN_TOKEN_LENGTH = 8

#: Separators that make a token look like a BRANCH NAME or a CARD ID rather
#: than an English word. A token must contain one of these to count, which
#: is what drops "container" and "released" while keeping
#: "relocation-residency-20260808" and "feat/session-carry".
_SLUG_SEPARATORS = ("-", "_", "/")

#: Card statuses that mean the work is finished. Everything else — including
#: an unrecognised status — counts as IN FLIGHT, because an unknown status is
#: not evidence of completion.
_TERMINAL_STATUSES = frozenset({"done", "completed", "cancelled", "canceled"})

#: Card fields that can name a branch. ``command`` is included because a
#: card's reproduction command routinely carries the branch name verbatim.
_TOKEN_FIELDS = ("id", "title", "note", "command", "branch", "task", "goal")


def is_slug_shaped(token: str) -> bool:
    """True iff ``token`` could plausibly BE a branch name or a card id.

    Length alone is not enough — "container" is nine characters and is an
    English word that appears in half the fleet's card notes. Requiring a
    separator is what distinguishes a NAME from a WORD.
    """
    return len(token) >= MIN_TOKEN_LENGTH and any(
        sep in token for sep in _SLUG_SEPARATORS
    )


def _tokenise(value: object) -> set[str]:
    """Lowercase branch-shaped fragments of one field value."""
    if not isinstance(value, str):
        return set()
    tokens: set[str] = set()
    for chunk in value.replace(",", " ").replace(";", " ").split():
        token = chunk.strip().strip("`'\"()[]<>.:").lower()
        if is_slug_shaped(token):
            tokens.add(token)
    return tokens


def card_active_tokens() -> set[str] | None:
    """Tokens from every non-terminal card, or ``None`` when unavailable.

    The default :data:`ActiveRefs` implementation. Deliberately broad: it
    is cheaper to keep a branch nobody needed than to have to explain a
    deleted one.
    """
    try:
        from scitex_cards import list_tasks  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - any import failure is UNAVAILABLE
        return None
    try:
        cards = list_tasks()
    except Exception:  # noqa: BLE001 - an unresolvable store is UNAVAILABLE
        return None
    if cards is None:
        return None
    tokens: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        status = str(card.get("status", "")).strip().lower()
        if status in _TERMINAL_STATUSES:
            continue
        for field in _TOKEN_FIELDS:
            tokens |= _tokenise(card.get(field))
    return tokens


def branch_is_active(branch: str, tokens: set[str]) -> bool:
    """True iff ``branch`` overlaps any active token.

    Containment is checked BOTH ways: a card whose id is
    ``relocation-residency-20260808`` should keep a branch named
    ``relocation/residency``, and a card that merely says ``relocation``
    should keep it too. Both directions over-match rather than under-match,
    which is the direction this whole primitive leans.
    """
    needle = branch.strip().lower()
    if not needle:
        return False
    normalised = needle.replace("/", "-").replace("_", "-")
    for token in tokens:
        if not is_slug_shaped(token):
            continue
        candidate = token.replace("/", "-").replace("_", "-")
        if candidate in normalised or normalised in candidate:
            return True
    return False


# EOF
