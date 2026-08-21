# `_dialect` — one interface, two backends

Everything a backend does differently lives behind `Dialect`: parameter
style, identifier quoting, column types, upsert syntax, and how a
connection is opened. Callers of `scitex_dev.store` never write SQL and
never learn which engine they are on.

| File | Backend | Role |
|---|---|---|
| `__init__.py` | — | `Dialect` ABC, shared DDL, `get_dialect()` |
| `_sqlite.py` | SQLite | **regenerable local state only** |
| `_postgres.py` | Postgres | **the default for runtime state**, driver extra-gated |

## The two are not peers

**Postgres is the default for runtime state.** The per-host instance on
55432, synchronised across hosts. This is the fleet rule, not a
preference here — constitution §3, the operator's ruling of 2026-08-14:
*spec は設計書、状態は db*. Design belongs to git; state belongs to the
database.

**SQLite is for regenerable local state only.** A derived index, a
rebuildable cache — anything whose loss costs a recompute and nothing
else. The test is simple: if losing the file would lose a fact nobody
else holds, it is state, and it does not belong here.

Everything above the dialect is identical either way: same schema, same
oplog, same directed replay. The oplog does make multi-host replication
work over SQLite — that remains true, and it is *not* a reason to keep
state there. Replication of a local file is a recovery story, not a
source of truth.

### This file used to say the opposite, and that mattered

Until 2026-08-21 these documents declared "SQLite is the default /
Postgres is advanced" in four places. Nothing in the code enforced
either way — `get_dialect()` takes an explicit backend — so the sentence
*was* the mechanism. A fleet survey the same day counted **66 of 68**
live SQLite tables in one consumer package; whoever chose SQLite there
was following this file correctly. A default stated only in prose is
still a default.

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
