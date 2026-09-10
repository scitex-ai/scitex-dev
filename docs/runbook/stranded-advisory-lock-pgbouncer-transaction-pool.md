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
The recovery (`PAUSE`/`DISCARD ALL`/`RESUME`) is the one production-facing step —
it reconnects idle pooled server connections fleet-wide for a few seconds. Read the
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

`DISCARD ALL` on pgbouncer closes **idle** server connections and leaves any
server connection with an active transaction intact — which is precisely the shape
of the leaked lock (idle pooled backend) and precisely the shape we must NOT touch
(a busy backend). Wrap it in `PAUSE`/`RESUME` so no new client transactions start in
the discard window. This reconnects pool slots fleet-wide for a few seconds; it does
not terminate postgres backends for work and does not change any data or schema.

```
# pgbouncer admin console: find its port (default 6432) and admin user (pgbouncer)
# from the compose file's [pgbouncer] section.
$ psql "host=127.0.0.1 port=<admin_port> user=pgbouncer dbname=pgbouncer" -w
  PAUSE;            -- no new client connections enter the pool
  DISCARD ALL;      -- close idle server connections (releases the stranded lock);
                    -- idle-in-transaction / active connections are left alone
  RESUME;           -- reopen the pool
```

Confirm via `SHOW SERVERS` (admin console) that the server slot for `<holder_pid>`
dropped, and re-run the §1 survey: the key's `held` count returns to 0 and the
`waiting` count drains.

## 3. Verify end-to-end (no data change; just prove the pipeline moved)

- The previously-waiting `sac-listen` operations complete (their `SELECT
  pg_advisory_lock(hashtext($1))` now acquires).
- On one of the affected bridges (e.g. 19012/19011/19000) issue a `/v1/turn` and
  confirm it returns (not hangs) and that the expected task row appears in the
  cards store.
- Re-run the §1 survey a few minutes later: no advisory lock has re-stranded, which
  is the signal the scitex-dev fix is live (or that no relaunch hit the DDL path).

## Rollback

- `PAUSE`/`RESUME` has no data effect; if anything looks wrong mid-window, run
  `RESUME` immediately to reopen the pool. There is no partial state to unwind.
- `DISCARD ALL` only closed idle server connections. No DDL or DML ran, so there is
  nothing to roll back in the database — the "rollback" is simply that the pool
  re-establishes connections on the next use.
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
