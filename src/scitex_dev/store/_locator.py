#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locators — typed, and one of them refuses to be a path.

The measured failure
--------------------
scitex-cards found directory trees on one host named::

    .../proj/scitex-cards/postgresql:/scitex_cards@127.0.0.1:5432/runtime/todo.db

Each is a real SQLite file that nothing reads. They are what
``Path("postgresql://scitex_cards@127.0.0.1:5432/...")`` does when something
``mkdir``s it relative to the process CWD: the DSN is not rejected, it is
accepted as a relative path and materialised as directories.

**Two of them, not thirteen.** The first report said 13; scitex-db caught
that it was one directory counted through thirteen symlinks, and
scitex-cards corrected it within the hour. The accurate number is recorded
here deliberately — an inflated one invites the next reader to check, find
two, and discount the whole finding.

Two is enough, because the argument was never the count. It is the SPREAD:
three separate sites made the same ``Path(dsn)`` mistake within a single
day. A ``str`` locator will reach ``Path()`` eventually, since a string
that happens to describe a location is indistinguishable from a path to
every API that takes one.

The fix is a type, not a convention
-----------------------------------
:class:`PostgresDsn` defines ``__fspath__`` and RAISES from it. So
``Path(dsn)``, ``open(dsn)``, ``os.makedirs(dsn)`` and everything else in
the filesystem API fail loudly, at the call, naming what went wrong —
rather than silently creating a directory named after a database.

:class:`SqlitePath` is genuinely a path and implements ``__fspath__``
normally. The asymmetry is the point: the type says which of the two a
locator is, so the question is answered by the type system instead of by
whoever is reading the code that day.

``str(PostgresDsn)`` is also deliberately NOT the raw DSN. It renders a
credential-free summary, so a DSN interpolated into a log line or an error
message cannot leak a password — and cannot accidentally round-trip into
something path-shaped either. The real connection string is available as
``.dsn``, which a caller has to ask for by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlsplit

__all__ = ["PostgresDsn", "SqlitePath", "StoreLocator"]

#: Suffix for SQLite stores. Fixed by convention, not preference — scitex-io
#: registers a loader for `.db` only, so any other suffix stops round-tripping
#: through `stx.io.load()`.
DB_SUFFIX: Final[str] = ".db"


@dataclass(frozen=True, slots=True)
class SqlitePath:
    """A SQLite store's location. Genuinely path-like."""

    path: Path

    def __post_init__(self) -> None:
        if not str(self.path).endswith(DB_SUFFIX):
            raise ValueError(
                f"SQLite locator {self.path!s} must end in {DB_SUFFIX!r}. The "
                "ecosystem runtime-state-DB convention fixes this suffix "
                "because scitex-io's load dispatch registers only '.db'."
            )

    def __fspath__(self) -> str:
        """Path-like, legitimately: this IS a file."""
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)

    @property
    def parent(self) -> Path:
        """The directory the store file lives in."""
        return self.path.parent


@dataclass(frozen=True, slots=True)
class PostgresDsn:
    """A Postgres connection string. Deliberately NOT path-like.

    Passing one to any filesystem API raises :class:`TypeError` naming the
    mistake, instead of creating a directory named after the database.
    """

    dsn: str

    def __post_init__(self) -> None:
        if not (self.dsn.startswith("postgres://") or self.dsn.startswith("postgresql://")):
            raise ValueError(
                f"Postgres DSN {self.dsn!r} must start with 'postgres://' or "
                "'postgresql://'. A bare host name would be parsed as a path "
                "by some drivers and silently connect somewhere else."
            )

    def __fspath__(self) -> str:
        """Always raises. This is the whole point of the type.

        ``Path()``, ``open()`` and ``os.makedirs()`` all route here, so a
        DSN reaching the filesystem API fails at the call site rather than
        materialising as directories.

        One wrinkle worth knowing before "fixing" it: ``pathlib`` CATCHES
        ``TypeError`` from ``__fspath__`` and replaces it with its own
        generic "argument should be a str or an os.PathLike object"
        message. So ``Path(dsn)`` still refuses — which is the part that
        matters — but the explanation below is only visible on the direct
        routes (``os.fspath``, ``open``). Raising a non-``TypeError`` to
        dodge the masking would be worse: callers that legitimately catch
        ``TypeError`` around path coercion would stop catching this.
        """
        raise TypeError(
            f"A Postgres DSN is not a filesystem path, and {self.safe()} was "
            "passed to an API that takes one (Path(), open(), makedirs(), "
            "...).\n"
            "\n"
            "This is a MEASURED failure, not a hypothetical: doing it "
            "produced directory trees named "
            "'postgresql:/<user>@<host>:<port>/runtime/todo.db' on a live "
            "host, each a real SQLite file that nothing reads, created "
            "relative to whatever the process CWD happened to be. Two of "
            "them, from three separate call sites in one day.\n"
            "\n"
            "If you want the connection string, ask for it by name: "
            "`target.dsn`. If you wanted a file, this store is not "
            "file-backed — check `target.is_file_backed` first, or use "
            "`target.path`, which is None for Postgres."
        )

    def __str__(self) -> str:
        """A credential-free summary, so logs cannot leak a password."""
        return self.safe()

    def safe(self) -> str:
        """A credential-free SUMMARY, marked as one so it is not misread.

        Rendered as ``postgres[host=… db=…]`` rather than as something
        shaped like a DSN. The previous form was ``postgres://<host>/<db>``,
        which reads as a connection string a caller might try to use — and
        for a SOCKET DSN it was also WRONG: libpq puts the socket directory
        in the ``host=`` QUERY PARAMETER, so ``urlsplit().hostname`` is
        None and every socket locator rendered as ``postgres://?/scitex``.

        MEASURED CONSEQUENCE, 2026-08-20: sac read ``str(locator)``, saw
        ``postgres://?/scitex``, and came within one message of reporting
        that this package's DSN GENERATOR was emitting a broken string. The
        generator was fine; the mask was lying in a DSN-shaped way. A
        summary that cannot be told from the thing it summarises will
        eventually be used as the thing.

        The real connection string is reached BY NAME (``locator.dsn``),
        which is what the docstring on ``StoreTarget.dsn`` already says.
        """
        parts = urlsplit(self.dsn)
        # Socket DSNs carry the directory in `?host=`; TCP DSNs in the
        # authority. Check both, so the summary describes what is actually
        # being connected to rather than only the TCP shape.
        host = parts.hostname
        if not host:
            host = parse_qs(parts.query).get("host", [""])[0]
        port = parts.port
        if not port:
            port = parse_qs(parts.query).get("port", [""])[0] or None
        database = parts.path.lstrip("/") or "?"

        bits = [f"db={database}"]
        if host:
            bits.insert(0, f"host={host}")
        if port:
            bits.append(f"port={port}")
        return f"postgres[{' '.join(bits)}]"


#: Either kind of locator. Union rather than a base class: the two have
#: genuinely different capabilities, and a shared base would invite exactly
#: the "treat them the same" code this type exists to prevent.
StoreLocator = SqlitePath | PostgresDsn

# EOF
