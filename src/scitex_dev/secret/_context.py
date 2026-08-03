#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``Context`` — the one thing a leaf passes to say WHOSE secret it wants.

The same leaf app runs in situations that look nothing alike:

    standalone            one OS user, a terminal, files under ~
    inside scitex-hub     a Django process serving many users at once
    a user logs in        the answer now depends on WHO is asking
    a project is scoped   ...and on WHICH project they are in
    another user joins    ...and two people must reach the same secret

If each leaf works those cases out for itself, they diverge, and the ways they
diverge are silent — a leaf that quietly falls back to the process-wide store
inside a web request serves one user's credential to another and looks like it
worked. So the situation is never inferred: it is passed, as a value, and
derived from in exactly one place.

    Context(app="cards")                                  # standalone
    Context(app="cards", user="ywatanabe")                # personal
    Context(app="cards", group="scitex")                  # shared by a team
    Context(app="cards", user="ywatanabe", project="thesis")
    Context(app="cards", group="scitex", project="paper1")

OWNER IS EXACTLY ONE OF user OR group
-------------------------------------
A store has one owner, because the owner is what decides who can decrypt it.
Allowing both would make "whose recipients apply?" a question with two answers,
and a question like that gets resolved differently by each caller.

Membership is expressed in the same mechanism rather than a parallel one:
another person joining a group means their key is added to that group store's
recipients. There is no separate ACL table to keep in step, and nothing about
sharing differs between standalone and hub.

WHY `user=None` IS NOT "the current user"
------------------------------------------
``None`` means "no owner dimension at all" — the standalone case, where the OS
account IS the boundary. It never means "look one up". A helper that guessed
the current user would make the multi-user case silently succeed in a single
-user shape, which is precisely the failure this type exists to prevent.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Base of the fleet's runtime state. Every derived path hangs off this.
_HOME_ENV = "SCITEX_SECRET_HOME"

#: Absolute override of the FINAL store root, ignoring every other rule.
#: Kept because tests and tenant overlays already use it.
_ROOT_ENV = "SCITEX_DEV_SECRET_ROOT"

#: Path segments must not travel. A user, group or project name arrives from a
#: database, a URL or a form; `..` or `/` in one would walk out of the store
#: and into someone else's. Rejected at construction rather than sanitised,
#: because silently rewriting an identifier makes two different owners share a
#: store without either of them being told.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$")


#: Top-level names inside a store that the owner layout claims for itself.
#: A secret called ``users/token`` would want ``…/secret/users/token.gpg``,
#: while user ``token``'s store is the DIRECTORY ``…/secret/users/token/``.
#: One of them would end up inside the other, and which one depends on the
#: order they were created in.
RESERVED_SEGMENTS = frozenset({"users", "groups"})


def name_reservation_error(name: str) -> Optional[str]:
    """Why ``name`` cannot be a secret name here, or ``None`` if it can.

    Returns a message rather than raising so both the CLI (which renders it)
    and the library (which wraps it in a result) use the same words.

    NOTE — enforcement lives at the boundaries a caller actually goes through:
    the ``dev secret`` commands and ``resolve``. ``SecretStore`` predates this
    layout and does not check it; a direct ``SecretStore(...).store()`` can
    still create a colliding name. Closing that is a follow-up, and it waits on
    ``_store.py`` being split, since that file is already at its line budget.
    """
    head = name.split("/", 1)[0]
    if head in RESERVED_SEGMENTS:
        return (
            f"{name!r} starts with the reserved segment {head!r}. "
            f"`{head}/` holds per-owner stores, so a secret with that prefix "
            f"would collide with an owner directory. Choose another name."
        )
    return None


def _check_segment(kind: str, value: str) -> str:
    if not _SAFE_SEGMENT.match(value) or ".." in value:
        raise ValueError(
            f"unusable {kind} {value!r}: must match {_SAFE_SEGMENT.pattern} and "
            "contain no '..'. A path segment that can traverse would let one "
            "owner address another's store."
        )
    return value


@dataclass(frozen=True)
class Context:
    """Which app is asking, on whose behalf, in which scope."""

    app: str
    user: Optional[str] = None
    group: Optional[str] = None
    project: Optional[str] = None

    def __post_init__(self) -> None:
        _check_segment("app", self.app)
        for kind, value in (
            ("user", self.user), ("group", self.group), ("project", self.project)
        ):
            if value is not None:
                _check_segment(kind, value)

        if self.user is not None and self.group is not None:
            raise ValueError(
                f"context names both user={self.user!r} and group={self.group!r}: "
                "a store has ONE owner, and the owner decides the recipients. "
                "For a personal store pass user; for a shared one pass group."
            )
        if self.project is not None and self.owner is None:
            # A project scope with nobody in it has no owner, so no recipient,
            # so nothing could decrypt it. Refuse the incoherent shape here
            # rather than produce a path that can never hold a readable secret.
            raise ValueError(
                "project scope requires a user or a group: a project store "
                "belongs to someone, and the owner determines who can decrypt."
            )

    @property
    def owner(self) -> Optional[str]:
        """The single owning principal, or ``None`` when standalone."""
        return self.user if self.user is not None else self.group

    @property
    def is_standalone(self) -> bool:
        """True when the OS account is the whole boundary."""
        return self.owner is None

    @property
    def is_shared(self) -> bool:
        """True when the owner is a group, i.e. more than one person may read."""
        return self.group is not None

    def secret_root(self) -> Path:
        """The directory holding this context's ``*.gpg`` files.

        One derivation, used by every leaf. A leaf that builds this path itself
        is the bug this method exists to remove.

        THE APP IS ALWAYS FIRST::

            ~/.scitex/<app>/secret/                          standalone
            ~/.scitex/<app>/secret/users/<user>/             personal
            ~/.scitex/<app>/secret/groups/<group>/           shared
            ~/.scitex/<app>/secret/users/<u>/projects/<p>/   scoped

        Everything an app owns stays inside that app's directory, which is the
        convention the rest of ``~/.scitex`` already follows, and removing an
        app is removing one subtree. An earlier draft put the owner first
        (``~/.scitex/users/<user>/<app>/secret``) — that moved the app segment
        depending on which case you were in, so there was no single shape a
        leaf could rely on. One invariant beats four special cases.
        """
        override = os.environ.get(_ROOT_ENV)
        if override:
            return Path(override).expanduser()

        home = Path(os.environ.get(_HOME_ENV, "~/.scitex")).expanduser()
        root = home / self.app / "secret"
        if self.owner is None:
            return root

        root = root / ("groups" if self.is_shared else "users") / self.owner
        if self.project is not None:
            root = root / "projects" / self.project
        return root

    def describe(self) -> str:
        """A short label for logs. Never includes a secret or a value."""
        if self.owner is None:
            return f"{self.app} (standalone)"
        who = f"group={self.group}" if self.is_shared else f"user={self.user}"
        if self.project is None:
            return f"{self.app} ({who})"
        return f"{self.app} ({who}, project={self.project})"


__all__ = ["Context", "RESERVED_SEGMENTS", "name_reservation_error"]


# EOF
