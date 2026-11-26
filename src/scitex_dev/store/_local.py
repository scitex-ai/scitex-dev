#!/usr/bin/env python3
"""The per-user LOCAL store — what an unconfigured machine resolves to.

WHY THIS EXISTS (scitex-dev#1111, scitex-writer#516). Until 0.66.x an unset
``SCITEX_STORE_DSN`` resolved to ``postgresql://scitex-primary:55432/scitex``:
the private name of one fleet's central node, compiled into a public wheel.
Outside that fleet every store-backed step failed with a host the user had
never heard of; on a fleet host a fresh project silently wrote into the shared
central store. A deployment's address is that deployment's configuration, not
a library default — so the fleet now exports ``SCITEX_STORE_DSN`` in its own
environment, and the code default is a store the user owns.

WHAT IT IS. A real PostgreSQL cluster — the one engine; nothing here is a
file-backed tier — owned by the OS user, kept under
``$SCITEX_DIR/store/local`` (``SCITEX_DIR`` defaults to ``~/.scitex``):

    pgdata/        the cluster (``initdb`` on first use)
    run/           its UNIX socket; directory and socket are mode 0700
    postgres.log   the server log
    lock           serialises first-use initialisation across processes

It never listens on TCP (``listen_addresses = ''``), so it cannot collide with
another Postgres on a port and nothing off this machine can reach it. Trust
authentication is safe here for the same reason a file in ``$HOME`` is: only
the owning OS user can open a 0700 socket directory.

ZERO-CONFIG, NOT ZERO-INSTALL. The cluster is initialised and started on the
first CONNECT (never on resolution: :func:`host_store` stays inert). The
PostgreSQL server binaries are found on ``PATH``, in the Debian/Ubuntu,
Homebrew and conda layouts, or in the optional ``pgserver`` wheel
(``pip install 'scitex-dev[local-store]'``). When none is found this FAILS
LOUDLY naming every way to provide one; it never falls back to a remote host.

A HOST THAT MANAGES A FLEET NODE IS REFUSED. If ``~/.scitex/pg`` exists, this
machine runs a node of a shared deployment, and a process there that reached
the local default has simply lost its configuration. Starting a private store
for it would accept every write and diverge from the deployment with nothing
in any log to say so — the exact failure the no-fallback rule forbids. So it
is told to set ``SCITEX_STORE_DSN`` instead.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from ._errors import StoreTargetError

__all__ = [
    "LOCAL_DATABASE",
    "LOCAL_ROLE",
    "LOCAL_STORE_PORT",
    "ensure_local_store",
    "is_local_store_dsn",
    "local_store_dir",
    "local_store_dsn",
    "pg_bin",
    "refuse_if_managed_node",
]

#: The database every record kind lives in — the same name the fleet uses, so
#: a dump moves between the two without renaming anything.
LOCAL_DATABASE: Final[str] = "scitex"

#: The cluster's superuser. Named in the DSN on purpose: ``PGUSER`` is often
#: set for some OTHER server (a deployment role), and libpq would otherwise
#: present that role to this cluster, which has never heard of it.
LOCAL_ROLE: Final[str] = "scitex"

#: Only names the socket FILE (``.s.PGSQL.<port>``); the cluster opens no TCP
#: port. Never 5432, matching the rest of this package.
LOCAL_STORE_PORT: Final[int] = 55432  # stx-allow: STX-NL001 (a port)

#: A host carrying this directory manages a node of a shared deployment.
_MANAGED_NODE_PGDATA: Final[Path] = Path("~/.scitex/pg")

#: libpq/kernels cap a UNIX socket path near 104-108 bytes. Past this length
#: the socket moves to a short per-user directory under the temp dir.
_MAX_SOCKET_PATH: Final[int] = 100

_START_TIMEOUT_SECONDS: Final[int] = 60

#: How much of a failing command's output an error carries.
_OUTPUT_TAIL_CHARS: Final[int] = 1_500

#: DSNs this process has already brought up — one ``pg_ctl`` round per store
#: per process, not one per connection.
_ENSURED: set = set()
_ENSURED_LOCK = threading.Lock()


def _scitex_dir() -> Path:
    return Path(os.environ.get("SCITEX_DIR") or "~/.scitex").expanduser()


def local_store_dir() -> Path:
    """Root of the per-user local store (``$SCITEX_DIR/store/local``)."""
    return _scitex_dir() / "store" / "local"


def _socket_dir(root: Path) -> Path:
    """Where the socket lives: ``<root>/run``, or a short path if that is too long.

    A deep ``$HOME`` (a scratch directory, a CI workspace) can push
    ``<root>/run/.s.PGSQL.55432`` past the kernel's socket-path limit, and
    the server then refuses to start with an error about the path, not the
    length. The fallback is per user AND per store root, mode 0700, so two
    users or two ``SCITEX_DIR``\\s never share a socket.
    """
    preferred = root / "run"
    if len(str(preferred / f".s.PGSQL.{LOCAL_STORE_PORT}")) <= _MAX_SOCKET_PATH:
        return preferred
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return Path(tempfile.gettempdir()) / f"scitex-store-{uid}-{digest}"


def _dsn_prefix() -> str:
    return f"postgresql://{LOCAL_ROLE}@/"


def _dsn_query() -> str:
    from urllib.parse import quote

    socket_dir = _socket_dir(local_store_dir())
    return f"?host={quote(str(socket_dir), safe='/')}&port={LOCAL_STORE_PORT}"


def local_store_dsn(database: str = LOCAL_DATABASE) -> str:
    """The DSN of the per-user local store. Pure: creates and starts nothing."""
    return f"{_dsn_prefix()}{database}{_dsn_query()}"


def _local_database(dsn: str) -> str | None:
    """The database a DSN names on the local store, or None if it is not it."""
    prefix, query = _dsn_prefix(), _dsn_query()
    if not (dsn.startswith(prefix) and dsn.endswith(query)):
        return None
    database = dsn[len(prefix) : len(dsn) - len(query)]
    return database if database and "/" not in database else None


def is_local_store_dsn(dsn: str) -> bool:
    """Whether ``dsn`` names the per-user local store of THIS environment."""
    return _local_database(dsn) is not None


def refuse_if_managed_node() -> None:
    """Refuse the local default on a host that manages a deployment node."""
    managed = _MANAGED_NODE_PGDATA.expanduser()
    if managed.exists():
        raise StoreTargetError(
            "SCITEX_STORE_DSN is unset, and this host manages a node of a "
            f"shared SciTeX store ({managed} exists). A process here that "
            "reaches the local default has lost its configuration; starting a "
            "private store for it would accept every write and reach nobody.\n"
            "\n"
            "FIX: export SCITEX_STORE_DSN with this deployment's DSN in the "
            "environment of this process (shell profile, service unit, or "
            "container spec)."
        )


def pg_bin(name: str) -> str | None:
    """Locate a PostgreSQL server binary, or None.

    Order: ``PATH``; the Debian/Ubuntu versioned layout (kept off ``PATH``);
    Homebrew; conda (``$CONDA_PREFIX/bin``); the ``pgserver`` wheel. Within a
    layout the highest major version wins.
    """
    found = shutil.which(name)
    if found:
        return found
    patterns = (
        ("/usr/lib/postgresql", f"*/bin/{name}"),
        ("/opt/homebrew/opt", f"postgresql*/bin/{name}"),
        ("/usr/local/opt", f"postgresql*/bin/{name}"),
        ("/usr/pgsql", f"bin/{name}"),
    )
    for base, pattern in patterns:
        hits = sorted(Path(base).glob(pattern), key=_major_version, reverse=True)
        if hits:
            return str(hits[0])
    conda = os.environ.get("CONDA_PREFIX")
    if conda and (Path(conda) / "bin" / name).is_file():
        return str(Path(conda) / "bin" / name)
    try:
        from pgserver._commands import POSTGRES_BIN_PATH  # type: ignore
    except Exception:  # noqa: BLE001 - absent or broken: not a binary source
        return None
    candidate = Path(POSTGRES_BIN_PATH) / name
    return str(candidate) if candidate.is_file() else None


def _major_version(path: Path) -> int:
    """``16`` for ``.../postgresql/16/bin/x`` or ``.../postgresql@16/bin/x``."""
    digits = "".join(ch for ch in path.parts[-3] if ch.isdigit())
    return int(digits) if digits else 0


def _no_binaries_error() -> StoreTargetError:
    return StoreTargetError(
        "SCITEX_STORE_DSN is unset, so SciTeX uses a per-user local "
        f"PostgreSQL store under {local_store_dir()} — but no PostgreSQL "
        "server binaries (initdb, pg_ctl) were found to create it.\n"
        "\n"
        "Provide ONE of:\n"
        "  pip install 'scitex-dev[local-store]'   (bundled binaries; Python <= 3.12)\n"
        "  sudo apt install postgresql             (Debian/Ubuntu)\n"
        "  brew install postgresql@16              (macOS)\n"
        "  conda install -c conda-forge postgresql\n"
        "or point SCITEX_STORE_DSN at a PostgreSQL you already run, e.g.\n"
        "  export SCITEX_STORE_DSN=postgresql://user@host:5432/scitex\n"
        "\n"
        "Nothing falls back to a remote host: provenance is written only to a "
        "store you named or the one you own."
    )


def _run(command: list, *, stage: str, timeout: float) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        tail = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or ""
        if isinstance(tail, bytes):
            tail = tail.decode("utf-8", errors="replace")
        raise StoreTargetError(
            f"Could not {stage} the per-user local store under "
            f"{local_store_dir()} ({type(exc).__name__}).\n"
            f"Command: {' '.join(map(str, command))}\n"
            f"Output (tail): {str(tail)[-_OUTPUT_TAIL_CHARS:]}\n"
            f"Server log: {local_store_dir() / 'postgres.log'}\n"
            "PostgreSQL refuses to run as root; run as a normal user, or set "
            "SCITEX_STORE_DSN to a server you already run."
        ) from None


@contextlib.contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """An inter-process lock, so concurrent first uses initialise once.

    POSIX only; :func:`ensure_local_store` refuses Windows before reaching it.
    """
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _conf_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _initdb(initdb: str, pgdata: Path, socket_dir: Path) -> None:
    _run(
        [
            initdb,
            "-D",
            str(pgdata),
            "-U",
            LOCAL_ROLE,
            "-A",
            "trust",
            "--encoding=UTF8",
            "--locale=C",
        ],
        stage="initialise (initdb)",
        timeout=300,
    )
    with open(pgdata / "postgresql.conf", "a", encoding="utf-8") as conf:
        conf.write(
            "\n# --- scitex-dev per-user local store ---\n"
            "listen_addresses = ''\n"
            f"unix_socket_directories = {_conf_quote(str(socket_dir))}\n"
            "unix_socket_permissions = 0700\n"
            f"port = {LOCAL_STORE_PORT}\n"
        )


def _create_database(database: str) -> None:
    import psycopg

    with psycopg.connect(
        local_store_dsn("postgres"), autocommit=True, connect_timeout=10
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()
        if not exists:
            quoted = database.replace('"', '""')
            conn.execute(f'CREATE DATABASE "{quoted}"')


def ensure_local_store(database: str = LOCAL_DATABASE) -> str:
    """Initialise (first use) and start the per-user local store; return its DSN.

    Idempotent and safe to call concurrently from several processes. Raises
    :class:`StoreTargetError` — never falls back — when the server binaries
    are missing, the platform has no UNIX sockets, the store directory would
    not survive a container rebuild, or the server will not start.
    """
    dsn = local_store_dsn(database)
    with _ENSURED_LOCK:
        if dsn in _ENSURED:
            return dsn
    if sys.platform.startswith("win"):
        raise StoreTargetError(
            "SCITEX_STORE_DSN is unset and the per-user local store needs UNIX "
            "sockets, which this platform does not provide. Set "
            "SCITEX_STORE_DSN to a PostgreSQL server you run, e.g. "
            "postgresql://user@localhost:5432/scitex."
        )
    refuse_if_managed_node()
    initdb, pg_ctl = pg_bin("initdb"), pg_bin("pg_ctl")
    if not initdb or not pg_ctl:
        raise _no_binaries_error()

    root = local_store_dir()
    pgdata, log = root / "pgdata", root / "postgres.log"
    socket_dir = _socket_dir(root)
    # Imported here: _host imports this module to resolve the default.
    from ._host import require_durable_pgdata

    require_durable_pgdata(pgdata)
    with _file_lock(root / "lock"):
        root.chmod(0o700)
        socket_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        socket_dir.chmod(0o700)
        if not (pgdata / "PG_VERSION").is_file():
            _initdb(initdb, pgdata, socket_dir)
        status = subprocess.run(
            [pg_ctl, "-D", str(pgdata), "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
        if status.returncode != 0:
            _run(
                [
                    pg_ctl,
                    "-D",
                    str(pgdata),
                    "-l",
                    str(log),
                    "-w",
                    "-t",
                    str(_START_TIMEOUT_SECONDS),
                    "start",
                ],
                stage="start",
                timeout=_START_TIMEOUT_SECONDS + 30,
            )
        _create_database(database)
    with _ENSURED_LOCK:
        _ENSURED.add(dsn)
    return dsn


# EOF
