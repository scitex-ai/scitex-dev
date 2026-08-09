#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where a secret lives, derived from the ecosystem-wide scope contract.

``scitex_dev.scope`` defines WHO is asking and about WHAT for every SciTeX
app. This module answers one further question for one of them — where the
credential file sits — and it does so by *consuming* those types rather than
restating them. An earlier draft carried its own ``user`` / ``group`` /
``project`` fields; that was a second definition of the same idea, and a second
definition is the thing the scope contract exists to prevent.

    from scitex_dev.scope import Scope
    from scitex_dev.secret import SecretContext

    SecretContext(app="cards", scope=Scope.standalone())          # standalone
    SecretContext(app="cards", scope=Scope(owner="ywatanabe"))    # personal
    SecretContext(app="scholar", scope=Scope(owner="scitex"))     # an org
    SecretContext(app="writer",
                  scope=Scope(owner="ywatanabe", project="thesis"))

ONE OWNER NAMESPACE, NOT TWO
----------------------------
The shipped URL is ``scitex.ai/<user-or-org>/<project>``, and it does not say
which of the two an owner is — so the namespace is SHARED, exactly as on
GitHub, where a user and an organisation cannot take the same name. An earlier
draft split the store into ``users/`` and ``groups/``; that split asked a
question the URL had already answered, and it would have let
``ywatanabe`` the user and ``ywatanabe`` the org own different stores while
addressing the same page. One ``owners/`` segment, and whether an owner is a
person or a team is a property of the Principal, never of the path.

THE APP IS ALWAYS FIRST::

    ~/.scitex/<app>/secret/                               standalone
    ~/.scitex/<app>/secret/owners/<owner>/                owned
    ~/.scitex/<app>/secret/owners/<owner>/projects/<p>/   scoped

Everything an app owns stays inside that app's directory — the convention the
rest of ``~/.scitex`` already follows — so removing an app is removing one
subtree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..scope import Scope

#: Base of the fleet's runtime state. Every derived path hangs off this.
_HOME_ENV = "SCITEX_SECRET_HOME"

#: Absolute override of the FINAL store root, ignoring every other rule.
#: Kept because tests and tenant overlays already use it.
_ROOT_ENV = "SCITEX_DEV_SECRET_ROOT"

#: The one top-level name inside a store that the layout claims for itself.
#: A secret called ``owners/token`` would want ``…/secret/owners/token.gpg``
#: while owner ``token``'s store is the DIRECTORY ``…/secret/owners/token/``.
#: One would end up inside the other, and which one depends on creation order.
RESERVED_SEGMENTS = frozenset({"owners"})


def name_reservation_error(name: str) -> Optional[str]:
    """Why ``name`` cannot be a secret name here, or ``None`` if it can.

    Returns a message rather than raising so the CLI (which renders it) and the
    library (which wraps it in a result) use the same words.

    NOTE — enforcement lives at the boundaries a caller actually goes through:
    the ``dev secret`` commands and ``resolve``. ``SecretStore`` predates this
    layout and does not check it, so a direct ``SecretStore(...).store()`` can
    still create a colliding name. Closing that waits on ``_store.py`` being
    split, since that file is already at its line budget.
    """
    head = name.split("/", 1)[0]
    if head in RESERVED_SEGMENTS:
        return (
            f"{name!r} starts with the reserved segment {head!r}. "
            f"`{head}/` holds per-owner stores, so a secret with that prefix "
            f"would collide with an owner directory. Choose another name."
        )
    return None


@dataclass(frozen=True)
class SecretContext:
    """An app plus the scope whose secrets are wanted.

    ``scope`` HAS NO DEFAULT — operator directive 2026-08-04, 「明示的に渡し
    たいなあと思っています」 (I would like it passed explicitly). Every caller
    states which scope it means, and a
    caller who forgets gets a TypeError at the call site.

    An earlier version defaulted to the empty ``Scope()``. That was safe in
    the sense that it did not guess a user, but it still let the most
    dangerous call — a request handler that forgot to pass the requesting
    user — construct successfully and quietly read the standalone store. A
    missing argument is a loud, immediate, unmissable failure; a defaulted
    one is a silent wrong answer. For the standalone case say so:

        SecretContext(app="writer", scope=Scope.standalone())
        SecretContext(app="writer", scope=Scope(owner=request.user.username))

    Neither form can be reached by accident, and both say what they mean.
    """

    app: str
    scope: Scope

    def __post_init__(self) -> None:
        # `Scope` validates its own segments (traversal, shape) at
        # construction, so there is nothing to re-check here. Only `app` is
        # ours, and it is validated the same way Scope validates its fields.
        Scope(owner=self.app)

    @property
    def is_standalone(self) -> bool:
        """True when the OS account is the whole boundary."""
        return self.scope.owner is None

    def secret_root(self) -> Path:
        """The directory holding this context's ``*.gpg`` files.

        One derivation, used by every leaf. A leaf that builds this path itself
        is the bug this method exists to remove.
        """
        override = os.environ.get(_ROOT_ENV)
        if override:
            return Path(override).expanduser()

        home = Path(os.environ.get(_HOME_ENV, "~/.scitex")).expanduser()
        root = home / self.app / "secret"
        if self.scope.owner is None:
            return root

        root = root / "owners" / self.scope.owner
        if self.scope.project is not None:
            root = root / "projects" / self.scope.project
        return root

    def describe(self) -> str:
        """A short label for logs. Never includes a secret or a value."""
        if self.scope.owner is None:
            return f"{self.app} (standalone)"
        if self.scope.project is None:
            return f"{self.app} (owner={self.scope.owner})"
        return (
            f"{self.app} (owner={self.scope.owner}, "
            f"project={self.scope.project})"
        )


__all__ = ["SecretContext", "RESERVED_SEGMENTS", "name_reservation_error"]


# EOF
