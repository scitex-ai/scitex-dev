# Recovery runbook — stranded session-level advisory lock(s) on the pooled central primary

## Why this exists

Before scitex-dev `fix/transaction-scoped-schema-lock`, `PostgresDialect.schema_lock`
took a **session-level** `pg_advisory_lock` and released it in `finally` on an
`autocommit` connection. Through pgbouncer in `pool_mode=transaction` the acquire
and the release can land on different server backends, so the release silently no-ops
and the lock strands forever on a long-lived pooled server connection. Every later
`pg_advisory_lock(hashtext(<same oplog>))` blocks behind it.

Symptom (compute-03, 2026-09-10): five `sac-listen` operations waited 28-42 min on
`SELECT pg_advisory_lock(hashtext($1))`; `pg_blocking_pids` pointed at one idle holder
backend; TUI bridges accepted TCP but `/v1/turn` hung; no tasks inserted.

The fix (transaction-scoped `pg_advisory_xact_lock` inside one explicit transaction)
stops NEW leaks. This runbook clears the ALREADY-stranded lock(s) without touching
data and without terminating backends for work.

## Ground rule

Only run this on the host that fronts the central primary (pgbouncer
`listen_addr` includes the fleet address). The survey is read-only and safe.
The recovery (`RECONNECT` followed by `WAIT_CLOSE`) is the one
production-facing step: it retires each pooled server connection after that
connection is released according to the configured pooling mode. Read the
"Rollback" section and get the go-ahead before running it.

## 1. Survey (read-only — run first, and again after recovery to prove it worked)

Connect to postgres **directly, bypassing pgbouncer** (local socket, or the pgbouncer
server port the compose file points at — `* = host=127.0.0.1 port=55433`), as a role
that can read `pg_stat_activity`. A bare `SELECT` acquires no advisory lock, so this
is safe to run through the pool too, but direct is cleaner.

```sql
-- who holds which advisory lock, and who is waiting on it
SELECT l.classid, l.objid,
       l.pid            AS holder_pid,
       a.state          AS holder_state,
       a.application_name,
       left(a.query, 60) AS holder_last_query
FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
WHERE l.locktype = 'advisory' AND l.granted
ORDER BY l.classid, l.objid, l.pid;

-- per key: how many holders vs how many waiters (the backlog is the 'waiting' count)
SELECT l.classid, l.objid,
       count(*) FILTER (WHERE l.granted)  AS held,
       count(*) FILTER (WHERE NOT l.granted) AS waiting
FROM pg_locks l
WHERE l.locktype = 'advisory'
GROUP BY l.classid, l.objid
HAVING count(*) > 0
ORDER BY l.classid, l.objid;

-- is the specific holder idle? (a stranded session lock on an idle pooled backend is
-- exactly the shape this fixes; an ACTIVE-transaction holder is NOT safe to discard)
SELECT pid, state, wait_event_type, left(query, 60) AS last_query
FROM pg_stat_activity WHERE pid = <holder_pid>;
```

Interpretation: the stranded lock's holder is in state `idle` (session lock, no open
transaction). If it ever shows `idle in transaction` / `active`, STOP and do not run
the recovery — that backend has work in flight and is not the leaked-lock shape.

## 2. Recovery (production-facing; gated)

Use PgBouncer's administrative `RECONNECT` command. It marks each open server
connection for closure after that connection is released according to the pool
mode. The idle connection holding the stranded session lock can therefore close
immediately, while a connection still serving a transaction is not interrupted.
New server connections may be created as needed. `WAIT_CLOSE` provides a bounded,
observable completion point for the retirement rather than treating command
acceptance as proof that the old backend disappeared.

Both commands and the `close_needed` observation field were added in PgBouncer
1.9. Check `SHOW VERSION` first; on an older deployment, stop rather than
improvising another disconnect command. See the official
[process-control command reference](https://www.pgbouncer.org/usage#process-controlling-commands).

```
# pgbouncer admin console: find its port (default 6432) and admin user (pgbouncer)
# from the compose file's [pgbouncer] section.
$ psql "host=127.0.0.1 port=<admin_port> user=pgbouncer dbname=pgbouncer" -w
  SHOW VERSION;                 -- must be PgBouncer 1.9 or newer
  SHOW SERVERS;                 -- record database/user/remote_pid and state first
  RECONNECT <pgbouncer_db>;     -- retire connections after release
  WAIT_CLOSE <pgbouncer_db>;    -- wait until close_needed is clear
```

`<pgbouncer_db>` is the database name shown by `SHOW SERVERS`, not necessarily
PostgreSQL's physical database name. Confirm that the row whose `remote_pid`
equals `<holder_pid>` disappeared, and re-run the §1 survey: the key's `held`
count returns to 0 and the `waiting` count drains.

Do **not** substitute SQL `DISCARD ALL`: it is a PostgreSQL session-reset query,
not the PgBouncer administrative command that retires pooled server connections.

## 3. Verify end-to-end (no data change; just prove the pipeline moved)

- The previously-waiting `sac-listen` operations complete (their `SELECT
  pg_advisory_lock(hashtext($1))` now acquires).
- On one of the affected bridges (e.g. 19012/19011/19000) issue a `/v1/turn` and
  confirm it returns (not hangs) and that the expected task row appears in the
  cards store.
- Re-run the §1 survey a few minutes later: no advisory lock has re-stranded, which
  is the signal the scitex-dev fix is live (or that no relaunch hit the DDL path).

## Rollback

- `RECONNECT` changes no data or schema. Connections already marked for closure
  cannot be unmarked; PgBouncer opens replacements as clients need them.
- If `WAIT_CLOSE` does not return, inspect `SHOW SERVERS` rather than escalating
  to `KILL`: a remaining `close_needed=1` connection has not yet been released.
  `KILL` immediately drops client and server connections and is outside this
  runbook's authorization.
- If the stranded holder is NOT idle (step 1 showed a transaction), this procedure is
  the wrong tool and you must NOT run it; escalate to the operator, because the only
  other lever is terminating that specific backend, which this task forbids without
  explicit evidence.

## Preventing recurrence

Merge + deploy scitex-dev `fix/transaction-scoped-schema-lock` (transaction-scoped
`pg_advisory_xact_lock`) and upgrade the SAC agents that construct `Store`s against
the pooled central primary. Transaction mode pins a whole `BEGIN..COMMIT` to one
server backend, so the acquire and its release can no longer split. Do not change
pgbouncer `pool_mode` to `session` as the fix — that trades this leak for unbounded
server connections and changes fleet capacity; the code fix is the correct layer.
