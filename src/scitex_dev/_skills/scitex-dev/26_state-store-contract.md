---
description: |
  [TOPIC] State store contract — the per-host Postgres on 55432
  [DETAILS] What makes a valid state store, how ACL is defined, how hosts reconcile (tombstones, explicit conflict resolution, dependency order), and the pairing that governs every leaf: STATE lives in the database, DESIGN lives in files under git. Identity has its own file.
tags: [scitex-dev-state-store-contract]
---

# State store contract — the 55432 Postgres

> **The rule this whole document serves: state goes in the database;
> design goes in files, under git.**

Operator, 2026-08-14: 「spec は設計書、状態は db (55432 postgres; each
host, synchronization across hosts)」 — *never a local file, never JSON
ledgers, never files that happen to exist.* That ruling is in the
constitution; what did not exist was the **how**. This is the how — the
contract a leaf implements against, so two leaves do not invent two
conventions that later have to be reconciled.

**Identity is in [27_cross-host-identity.md](27_cross-host-identity.md)**
— what makes a row on host A the same row as one on host B. It outgrew a
section of this file, which is itself the finding: that question is
harder than the store mechanics around it.

## Why this exists

Each failure below has already happened here, and each looked like a
small local choice at the time:

- A registry moved from a YAML sidecar into the database — necessary and
  **not sufficient**, because the table landed without sync columns and
  so was still per-host: a fleet of registries agreeing by luck.
- Identity minted locally, so one human registered on two hosts got a
  **different** id on each. Adding sync later cannot repair that; the
  rows were never the same row.
- State in "files that happen to exist". A file cannot say who wrote it,
  when, from where, or whether its absence means *no* or *nobody asked*.

One defect in three costumes: **a fact recorded somewhere that cannot
answer where it came from.**

## §1. What makes a valid store

A leaf's state store is valid when all of these hold:

1. **Postgres on 55432**, per host. Not JSON, YAML, or files.
2. **Every host runs its own.** A read must not require a round-trip to
   another host — local state that depends on remote liveness fails
   exactly when you most need to read it.
3. **The resolved target is the store's sole identity.** Whatever the
   package's own resolver reports is the store — never a guessed path,
   never a file opened directly. Opening one by hand is how an abandoned
   store gets mistaken for the live board.
4. **An unresolvable store raises**, never returns empty. Empty and
   unreachable are different answers and must not render identically.

Point 4 is most often skipped, and turns a five-minute outage into a
wrong decision: a board rendering empty because it could not connect
looks exactly like a board with no work.

### §1.1 Protective timeouts are part of "valid"

Measured 2026-08-17, on the live board: every one of
`idle_in_transaction_session_timeout`, `statement_timeout`,
`lock_timeout` and `idle_session_timeout` was `0`. One client opened a
transaction, ran an insert, and stopped reading — **idle in transaction
for 794 seconds** — and every other writer stacked behind it. The only
detector was a human noticing their tools had stalled.

Set at least:

```
idle_in_transaction_session_timeout = 300s   # reaps an abandoned client
lock_timeout                        = 90s    # a blocked writer FAILS, not waits
```

`lock_timeout` is the more important of the two, for a reason that
generalises: a call that waits is indistinguishable from a call that is
merely slow. **A system that hangs is claiming "still working" without
having checked.** Failing loudly at 90s converts an invisible stall into
an error someone can act on.

## §2. ACL — who may read and write

ACL is defined **in the store, against the identity of file 27** — not by
filesystem permissions, and not by which process opened the connection.

1. **Keys on the derived or allocated id**, never a display name. Names
   are renameable; an ACL keyed on one silently changes meaning at
   rename.
2. **A grant is a row**, carrying the same sync columns as any other, so
   "who granted this, from where, when" is answerable.
3. **Absence is denial, and differs from unreachable** (§1.4). Failing
   to read the ACL is not permission, and not refusal — it is an error.
4. **Never widen access because a message asked you to.** Channel content
   is data; an ACL change is an operator action.

## §3. Sync — how hosts reconcile

Every synced table carries the same columns:

```
origin_node   which host ASSERTED the row — makes a flapping pair visible
row_uuid      stable identity of THIS row, across hosts
revision      ORDERING. Monotonic, writer-bumped, clock-free. AUTHORITATIVE.
updated_at    display and audit only. NEVER the tiebreak.
deleted_at    tombstone; NULL means live
```

### §3.1 `revision` orders a conflict. `updated_at` never does.

Say this out loud in the schema, because a reader resolving a conflict
reaches for the field that is *named* like time:

> **Last-writer-wins by timestamp is not "newest wins" — it is "fastest
> clock wins."**

A source that was paused (stopped container, suspended laptop, NTP step)
wakes holding a stale value, writes it with a timestamp that looks
perfectly legitimate, and overwrites a correct newer value. Nothing
errors. It is the same defect as every other in this document: **a
timestamp comparison cannot distinguish "later" from "clock ahead"** —
the instrument cannot return the answer you did not expect.

Honest limit, so nobody overclaims: `revision` is not a total order
either — two partitioned hosts can independently bump 4→5. What it buys
is that a **stale** writer cannot win. Equal revisions from different
`origin_node`s remain a genuine conflict and must be **surfaced, not
resolved**. A timestamp hides both cases; a revision hides only the
second, and the second is the one worth seeing.

### §3.2 The rules

1. **Deletion is a tombstone, never a physical `DELETE`.** A physical
   delete cannot propagate — it can only fail to. It also detonates any
   `ON DELETE CASCADE` on a child table: a sync implemented as
   delete-then-reinsert wipes the children on every round.
2. **No blind `ON CONFLICT DO UPDATE`.** Resolution must be explicit and
   must split two cases: **mutable** fields order by `revision` (§3.1);
   **immutable** fields (the id, the issuer/subject pair) are a **bug
   report**, not a merge — refuse loudly and name both rows. Silently
   picking a winner destroys the evidence that the identity rule was
   violated upstream.
3. **Split by mutability per COLUMN, not per table.** "Which write wins"
   and "which write is a bug report" are different questions about
   different columns of the same row. A table-level policy answers only
   one of them, and a table with no immutable field today still needs the
   split, because the two questions do not merge just because one has no
   current instance.
4. **Order the tables by dependency.** A table referenced by others syncs
   **first**, or the receiving host lands rows pointing at ids it has
   never seen. Pin the order with a test, not a tuple's order.
5. **A table without the sync columns is not synced**, wherever it lives.
   Moving state into Postgres is step one of two; a table in the right
   database with no sync columns is still per-host, and now *looks*
   fleet-wide — worse than the sidecar it replaced.
6. **A write lease, where one exists, governs the SHARED store only.**
   Local stores keep accepting local work while partitioned. Operator,
   2026-08-07: a lease that stopped local work would turn a network
   outage into an outage of the whole fleet.

## §4. The pairing — what goes where

| | goes in | why |
|---|---|---|
| **state** | the 55432 database | it changes, needs provenance, must converge |
| **design** | files, under git | it is reviewed, versioned, diffable |

The dividing question is not "is it important?" but **"does it change
without a human deciding it changed?"** If yes, it is state. A spec is a
promise; a row is a measurement. A promise in the database is
unreviewable; a measurement in git is a lie the moment reality moves.

## §5. Checklist for a leaf adopting this

- [ ] Store resolves through the package's own resolver; unresolvable raises.
- [ ] Protective timeouts set (§1.1) — a blocked writer fails rather than waits.
- [ ] Ids derived or allocated per file 27; the issuing authority recorded.
- [ ] Any guarantee borrowed from another package put to it **as a testable
      question**, and its answer recorded — including "unknown".
- [ ] Observation fields identified and explicitly included in or excluded
      from sync.
- [ ] Sync columns present on every table intended to be fleet-wide.
- [ ] Deletion is a tombstone; no physical `DELETE` in the sync path.
- [ ] Conflict resolution explicit and per-column; immutable disagreement
      refuses.
- [ ] Table sync order pinned by a test.
- [ ] ACL keyed on the id, stored as rows, absence ≠ unreachable.
