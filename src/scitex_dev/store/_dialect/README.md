# `_dialect` — one interface, two backends

Everything a backend does differently lives behind `Dialect`: parameter
style, identifier quoting, column types, upsert syntax, and how a
connection is opened. Callers of `scitex_dev.store` never write SQL and
never learn which engine they are on.

| File | Backend | Role |
|---|---|---|
| `__init__.py` | — | `Dialect` ABC, shared DDL, `get_dialect()` |
| `_sqlite.py` | SQLite | **the default** |
| `_postgres.py` | Postgres | **advanced**, driver extra-gated |

## The two are not peers

**SQLite is the default.** A single file under `runtime/`, no daemon,
right for every store that lives on one host. Note that "SQLite" does not
mean "single machine" — the oplog makes multi-host replication work
anyway. It means the *storage* is local and the *sharing* is the
replication layer's job.

**Postgres is advanced.** Reach for it when a store needs concurrent
writers from several hosts against one database, or outgrows a file.
Everything above the dialect is identical: same schema, same oplog, same
directed replay.

## Asking for Postgres without the driver raises

`get_dialect(Backend.POSTGRES)` with no `psycopg` installed raises
`DialectUnavailableError` naming the extra to install. It does **not** fall
back to SQLite. A caller that asked for a shared database and silently
received a private local file would watch every write succeed while no peer
ever saw one — the failure would surface as "the other host is missing
data", days away from its cause.

## Connection settings are chosen, not inherited

SQLite connections set WAL journalling (readers do not block the writer),
`synchronous=NORMAL` (durable across process crashes with WAL; affordable
for high-frequency appends), `foreign_keys=ON` (SQLite defaults this OFF
*per connection*, so constraints declared in DDL are otherwise silently
unenforced), and a busy timeout (queue for a lock rather than fail
instantly).

## No dialect emits DELETE, DROP or TRUNCATE

Enforced by a test that scans the generated SQL, not by convention. Hiding
is a flag update. The rule survives someone later adding a well-meaning
cleanup helper, which is the whole reason it is mechanical.

## Adding a backend

Subclass `Dialect`, implement `connect` / `placeholder` / `quote` /
`column_type` / `upsert_sql`, and register it in `get_dialect`. The shared
`create_sql` builds the three tables (`<name>_rows`, `<name>_oplog`,
`<name>_cursor`) from those primitives, so a new backend does not restate
the schema — and cannot drift from it.
