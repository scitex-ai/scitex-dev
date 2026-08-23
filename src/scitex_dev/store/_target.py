#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``StoreTarget`` — which store, on which backend, at which locator.

A target is inert: constructing one opens nothing and creates nothing. It
is the value you pass around, log, compare and put in a card, so that
"which store did that write actually land in?" has an answer that does not
require re-deriving path resolution at the call site.

The locator is TYPED, not a string
-----------------------------------
``target.locator`` is a :class:`~._locator.SqlitePath` or a
:class:`~._locator.PostgresDsn`, never a bare ``str``. A DSN passed to any
filesystem API raises instead of being materialised as directories named
after the database — see :mod:`._locator` for the measured instances of
that happening in production.

``StoreTarget`` itself is likewise not path-like: it defines no
``__fspath__``, so ``Path(target)`` is a ``TypeError`` rather than a
stringified dataclass repr turned into a directory.

Path convention
---------------
LEGACY SQLite targets sit at
``<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db``, resolved
through ``scitex_config``'s ``runtime_path()`` rather than a
``Path.home()`` literal. That path is described here so existing files
remain findable; it is NOT a layout to place new state into. See the ecosystem skill
``01_ecosystem/13_runtime-state-db-layout.md``: ``runtime/`` is the single
subtree redirected off shared/GPFS filesystems.

That leaf's ``.db`` NAMING convention is WITHDRAWN (constitution §3,
2026-08-23 -- a ``.db`` file is SQLite, and runtime state now lives only
in the per-host PostgreSQL on 55432). The redirect rationale survives and
is why this resolves through ``runtime_path()``; the storage engine it
once implied does not. Do not read this docstring as sanctioning a new
``.db`` file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ._errors import StoreTargetError
from ._locator import DB_SUFFIX, PostgresDsn, SqlitePath, StoreLocator

__all__ = ["Backend", "DB_SUFFIX", "StoreTarget"]


class Backend(str, Enum):
    """The storage engines this primitive speaks."""

    #: The default. Zero-setup, single-file, WAL-mode.
    SQLITE = "sqlite"
    #: Advanced. For stores that outgrow one host or need real concurrency.
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
                f"StoreTarget.locator must be a SqlitePath or PostgresDsn, "
                f"not a str ({self.locator!r}). A string locator is the bug "
                "this type exists to prevent: it is indistinguishable from a "
                "path to every API that takes one, and a DSN passed to Path() "
                "silently becomes a directory tree named after the database. "
                "Use StoreTarget.sqlite(...) or StoreTarget.postgres(...)."
            )
        expected = SqlitePath if self.backend is Backend.SQLITE else PostgresDsn
        if not isinstance(self.locator, expected):
            raise StoreTargetError(
                f"Backend {self.backend.value!r} needs a "
                f"{expected.__name__} locator, got "
                f"{type(self.locator).__name__}."
            )

    # -- constructors -----------------------------------------------------
    @classmethod
    def for_package(
        cls,
        pkg: str,
        *,
        name: str = "store",
        shard: "str | None" = None,
    ) -> "StoreTarget":
        """The conventional SQLite target for ``pkg``.

        ``<runtime>/<pkg>.db``, or ``<runtime>/<shard>/<pkg>.db`` with a
        shard subdirectory. Resolution goes through ``scitex_config``; this
        never builds a home-relative path itself.
        """
        try:
            from scitex_config._ecosystem import local_state
        except ImportError as exc:
            raise StoreTargetError(
                "scitex_config is required to resolve a package store path "
                f"({exc}). Install it, or construct the target directly with "
                "StoreTarget.sqlite(<explicit path>, pkg=...)."
            ) from None

        base = local_state.runtime_path(pkg)
        directory = base / shard if shard else base
        return cls.sqlite(directory / f"{pkg}{DB_SUFFIX}", pkg=pkg, name=name)

    @classmethod
    def sqlite(
        cls, path: "str | Path", *, pkg: str, name: str = "store"
    ) -> "StoreTarget":
        """A SQLite target at an explicit path."""
        return cls(
            backend=Backend.SQLITE,
            locator=SqlitePath(Path(path)),
            pkg=pkg,
            name=name,
        )

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
    def path(self) -> "Path | None":
        """The on-disk path, or ``None`` for backends that have none.

        ``None`` means "this backend is not file-backed", never "unknown".
        """
        return self.locator.path if isinstance(self.locator, SqlitePath) else None

    @property
    def dsn(self) -> "str | None":
        """The connection string, or ``None`` for file-backed backends.

        Asked for BY NAME, deliberately: ``str(locator)`` renders a
        credential-free summary, so a DSN cannot leak a password into a log
        line by accident.
        """
        return self.locator.dsn if isinstance(self.locator, PostgresDsn) else None

    @property
    def is_file_backed(self) -> bool:
        """Whether :attr:`path` is meaningful."""
        return self.backend is Backend.SQLITE

    def exists(self) -> "bool | None":
        """Whether the store exists.

        ``True`` / ``False`` for file-backed stores; ``None`` — *unknown* —
        for Postgres, where answering would require connecting. The caller
        must handle the third value rather than reading ``None`` as "no".
        """
        path = self.path
        return path.exists() if path is not None else None

    def describe(self) -> str:
        """One-line human form for logs and card notes. Credential-free."""
        return (
            f"{self.backend.value}:{self.locator} "
            f"(pkg={self.pkg}, store={self.name})"
        )

# EOF
