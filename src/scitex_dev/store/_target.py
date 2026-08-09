#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``StoreTarget`` — which store, on which backend, at which locator.

A target is inert: constructing one opens nothing and creates nothing. It
is the value you pass around, log, compare and put in a card, so that
"which store did that write actually land in?" has an answer that does not
require re-deriving path resolution at the call site.

Path convention
---------------
SQLite targets follow the fleet's runtime-state-DB layout —
``<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db``, resolved
through ``scitex_config``'s ``runtime_path()`` rather than a
``Path.home()`` literal. See the ecosystem skill
``01_ecosystem/13_runtime-state-db-layout.md``: ``runtime/`` is the single
subtree that gets redirected off shared/GPFS filesystems, and ``.db`` is
the only suffix scitex-io's load dispatch recognises.

Postgres targets carry a DSN instead and have no path at all. That
asymmetry is deliberate and explicit — a target reports which of the two
it is rather than offering a ``path`` that is sometimes meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from ._errors import StoreTargetError

__all__ = ["Backend", "StoreTarget"]


class Backend(str, Enum):
    """The storage engines this primitive speaks."""

    #: The default. Zero-setup, single-file, WAL-mode.
    SQLITE = "sqlite"
    #: Advanced. For stores that outgrow one host or need real concurrency.
    POSTGRES = "postgres"


#: Suffix for SQLite stores. Fixed by convention, not preference — scitex-io
#: registers a loader for `.db` only, so any other suffix stops round-tripping
#: through `stx.io.load()`.
DB_SUFFIX: Final[str] = ".db"


@dataclass(frozen=True, slots=True)
class StoreTarget:
    """A resolved, comparable pointer to one store."""

    backend: Backend
    locator: str
    pkg: str
    name: str

    def __post_init__(self) -> None:
        if not self.locator:
            raise StoreTargetError(
                f"StoreTarget for package {self.pkg!r} has an empty locator. "
                "A SQLite target needs a file path; a Postgres target needs a "
                "DSN. Neither is guessed."
            )
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
        if self.backend is Backend.SQLITE and not self.locator.endswith(DB_SUFFIX):
            raise StoreTargetError(
                f"SQLite locator {self.locator!r} must end in {DB_SUFFIX!r}. "
                "The ecosystem runtime-state-DB convention fixes this suffix "
                "because scitex-io's load dispatch registers only '.db'."
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

        ``<runtime>/<pkg>.db``, or ``<runtime>/<shard>/<pkg>.db`` when a
        shard subdirectory is given. Resolution goes through
        ``scitex_config``; this never builds a home-relative path itself.
        """
        try:
            from scitex_config._ecosystem import local_state
        except ImportError as exc:
            raise StoreTargetError(
                "scitex_config is required to resolve a package store path "
                f"({exc}). Install it, or construct the StoreTarget directly "
                "with an explicit locator via StoreTarget.sqlite(...)."
            ) from None

        base = local_state.runtime_path(pkg)
        directory = base / shard if shard else base
        return cls(
            backend=Backend.SQLITE,
            locator=str(directory / f"{pkg}{DB_SUFFIX}"),
            pkg=pkg,
            name=name,
        )

    @classmethod
    def sqlite(cls, path: "str | Path", *, pkg: str, name: str = "store") -> "StoreTarget":
        """A SQLite target at an explicit path."""
        return cls(backend=Backend.SQLITE, locator=str(path), pkg=pkg, name=name)

    @classmethod
    def postgres(cls, dsn: str, *, pkg: str, name: str = "store") -> "StoreTarget":
        """A Postgres target at an explicit DSN."""
        if not (dsn.startswith("postgres://") or dsn.startswith("postgresql://")):
            raise StoreTargetError(
                f"Postgres DSN {dsn!r} must start with 'postgres://' or "
                "'postgresql://'. A bare host name would be parsed as a "
                "path by some drivers and silently connect somewhere else."
            )
        return cls(backend=Backend.POSTGRES, locator=dsn, pkg=pkg, name=name)

    # -- views ------------------------------------------------------------
    @property
    def path(self) -> "Path | None":
        """The on-disk path, or ``None`` for backends that have none.

        ``None`` means "this backend is not file-backed", never "unknown".
        """
        return Path(self.locator) if self.backend is Backend.SQLITE else None

    @property
    def is_file_backed(self) -> bool:
        """Whether :attr:`path` is meaningful."""
        return self.backend is Backend.SQLITE

    def exists(self) -> "bool | None":
        """Whether the store exists.

        ``True`` / ``False`` for file-backed stores; ``None`` — *unknown* —
        for Postgres, where answering would require connecting. The caller
        must handle the third value rather than read ``None`` as "no".
        """
        path = self.path
        return path.exists() if path is not None else None

    def describe(self) -> str:
        """One-line human form for logs and card notes."""
        return f"{self.backend.value}:{self.locator} (pkg={self.pkg}, store={self.name})"

# EOF
