#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``StoreTarget`` — which store, on which backend, at which locator.

A target is inert: constructing one opens nothing and creates nothing. It
is the value you pass around, log, compare and put in a card, so that
"which store did that write actually land in?" has an answer that does not
require re-deriving path resolution at the call site.

The locator is TYPED, not a string
-----------------------------------
``target.locator`` is a :class:`~._locator.PostgresDsn`, never a bare
``str``. A DSN passed to any filesystem API raises instead of being
materialised as directories named after the database — see :mod:`._locator`
for the measured instances of that happening in production.

``StoreTarget`` itself is likewise not path-like: it defines no
``__fspath__``, so ``Path(target)`` is a ``TypeError`` rather than a
stringified dataclass repr turned into a directory.

One engine, so nothing to choose
--------------------------------
Runtime state lives in exactly one place: the per-host PostgreSQL on 55432,
synchronised across hosts. There is no second engine, no file-backed tier,
and no zero-setup default that a caller can arrive at by not deciding —
constitution §3, 2026-08-23. A target therefore carries a DSN and nothing
else, and :class:`Backend` has one member so that the field keeps naming
what it names rather than disappearing into an implicit assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ._errors import StoreTargetError
from ._locator import PostgresDsn, StoreLocator

__all__ = ["Backend", "StoreTarget"]


class Backend(str, Enum):
    """The storage engine this primitive speaks. There is one."""

    #: Per host, on 55432, synchronised across hosts.
    POSTGRES = "postgres"


@dataclass(frozen=True, slots=True)
class StoreTarget:
    """A resolved, comparable pointer to one store."""

    backend: Backend
    locator: StoreLocator
    pkg: str
    name: str

    def __post_init__(self) -> None:
        if not self.pkg:
            raise StoreTargetError(
                "StoreTarget.pkg is empty. The package short name decides "
                "where runtime state resolves and which agent owns it."
            )
        if not self.name or not self.name.isidentifier():
            raise StoreTargetError(
                f"StoreTarget.name {self.name!r} must be a valid identifier — "
                "it prefixes the store's table names."
            )
        if isinstance(self.locator, str):
            raise StoreTargetError(
                f"StoreTarget.locator must be a PostgresDsn, not a str "
                f"({self.locator!r}). A string locator is the bug this type "
                "exists to prevent: it is indistinguishable from a path to "
                "every API that takes one, and a DSN passed to Path() "
                "silently becomes a directory tree named after the database. "
                "Use StoreTarget.postgres(...)."
            )
        if not isinstance(self.locator, PostgresDsn):
            raise StoreTargetError(
                f"Backend {self.backend.value!r} needs a PostgresDsn "
                f"locator, got {type(self.locator).__name__}."
            )

    # -- constructors -----------------------------------------------------
    @classmethod
    def postgres(cls, dsn: str, *, pkg: str, name: str = "store") -> "StoreTarget":
        """A Postgres target at an explicit DSN."""
        return cls(
            backend=Backend.POSTGRES,
            locator=PostgresDsn(dsn),
            pkg=pkg,
            name=name,
        )

    # -- views ------------------------------------------------------------
    @property
    def dsn(self) -> str:
        """The connection string.

        Asked for BY NAME, deliberately: ``str(locator)`` renders a
        credential-free summary, so a DSN cannot leak a password into a log
        line by accident.
        """
        return self.locator.dsn

    def exists(self) -> None:
        """Whether the store exists — *unknown* without connecting.

        Always ``None``, and that is the honest answer rather than a missing
        method: a store lives in a database this process may not have opened,
        so presence cannot be decided by looking. Callers must handle the
        third value instead of reading ``None`` as "no".
        """
        return None

    def describe(self) -> str:
        """One-line human form for logs and card notes. Credential-free."""
        return (
            f"{self.backend.value}:{self.locator} "
            f"(pkg={self.pkg}, store={self.name})"
        )

# EOF
