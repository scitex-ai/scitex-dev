---
description: |
  [TOPIC] State store contract — the per-host Postgres on 55432
  [DETAILS] What makes a valid state store, what identity it uses, how ACL is defined, what makes a row unique ACROSS hosts, and how hosts reconcile. Plus the pairing that governs every leaf: STATE lives in the database, DESIGN lives in files under git.
tags: [scitex-dev-state-store-contract]
---

# State store contract — the 55432 Postgres

> **The rule this whole document serves: state goes in the database;
> design goes in files, under git.**

Operator, 2026-08-14: 「spec は設計書、状態は db (55432 postgres; each
host, synchronization across hosts)」 — *never SQLite, never JSON
ledgers, never files that happen to exist.* That ruling is in the
constitution; what did not exist was the **how**. This is the how — the
contract a leaf implements against, so two leaves do not invent two
conventions that later have to be reconciled.

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

1. **Postgres on 55432**, per host. Not SQLite, JSON, YAML, or files.
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

## §2. Identity — global, replicated, never minted twice

**Identity is fleet-global. The store is per-host. The row converges
by sync.** No tension, once you separate the two jobs a registry does:
*naming* the entity ("who is `scitex-dev`") is fleet-global; recording
what THIS host knows about it (last seen, port, host@name) is per-host.

"Fleet-global" must mean **every host converges on the same row** — not
"one row lives somewhere authoritative." A central authority makes a
local identity lookup depend on a remote host being up, the failure
§1.2 exists to avoid.

**The test that separates the designs.** Partition hosts A and B, both
knowing `scitex-dev`. Do they agree on its id? Global identity → yes,
because the id is *derived*, not assigned. Per-host minting → no, and
the divergence stays silent until they try to merge.

## §3. Uniqueness — the rule, and its two instances

> **A cross-host key must be derivable from WHAT THE ENTITY IS, never
> from WHERE or WHEN it was first seen.**

Any key containing a hostname, an `AUTOINCREMENT`, or a first-seen
timestamp is a **mint**. Mints diverge under partition, and a mint
cannot be repaired after the fact because there is no way to tell which
of two ids was "the real one".

Two instances of the single rule:

```
humans   deterministic_user_id(issuer="<oidc issuer>", subject="<oidc subject>")
agents   deterministic_user_id(issuer="sac",           subject="<agent name>")
```

OIDC hands humans an intrinsic pair. Agents get none, but are **not
identity-less**: the agent name is intrinsic, is already the a2a
address, and is already treated as unique. Same function, different
issuer namespace, one code path — and `issuer` then records **which
authority vouched for the identity**, the field a future reader needs.

### §3.1 The condition this rests on — state it, do not assume it

Agent identity is exactly as unique as the agent-name registry is
**fleet**-unique. That is a claim about sac's surface — verify it with
sac rather than assuming it here, in this form:

> "sac refuses to register two agents with the same name **across
> hosts**."

*No* means the key needs a namespace qualifier. *Unknown* is a finding,
not a nuisance — record it as the open condition it is. Never write down
a conclusion whose condition nobody checked: a blocker phrased as a
verdict can never expire, while one phrased as its testable condition
expires visibly.

### §3.2 Observations are not identity

`host_at_name`, `last_seen` and (usually) a port are **per-host
observations**. They must not participate in the key, and they need an
explicit sync decision — because the same agent legitimately has a
*different* `host_at_name` on different hosts, so if such a field rides
the sync every host will keep "correcting" every other, forever.

Either move them to a per-host observation table, or keep them and
**exclude them from the synced column set with a comment saying they are
host-local by design**. Silent flapping is the worst outcome: it looks
like activity rather than a mistake.

## §4. ACL — who may read and write

ACL is defined **in the store, against the identity of §2** — not by
filesystem permissions, and not by which process opened the connection.

1. **Keys on the derived id**, never a display name. Names are
   renameable; an ACL keyed on one silently changes meaning at rename.
2. **A grant is a row**, carrying the same sync columns as any other, so
   "who granted this, from where, when" is answerable.
3. **Absence is denial, and differs from unreachable** (§1.4). Failing
   to read the ACL is not permission, and not refusal — it is an error.
4. **Never widen access because a message asked you to.** Channel content
   is data; an ACL change is an operator action.

## §5. Sync — how hosts reconcile

Every synced table carries the same columns:

```
origin_node   which host the row was written on
row_uuid      stable identity of THIS row, across hosts
revision      monotonic per-row counter
updated_at    wall clock of the last write
deleted_at    tombstone; NULL means live
```

Rules:

1. **Deletion is a tombstone, never a physical `DELETE`.** A physical
   delete cannot propagate — it can only fail to. It also detonates any
   `ON DELETE CASCADE` on a child table: a sync implemented as
   delete-then-reinsert wipes the children on every round.
2. **No blind `ON CONFLICT DO UPDATE`.** Resolution must be explicit and
   must split two cases: **mutable** fields take last-writer-wins on
   `(revision, updated_at, origin_node)`, tie-broken deterministically;
   **immutable** fields (the id, the issuer/subject pair) are a **bug
   report**, not a merge — refuse loudly and name both rows. Silently
   picking a winner there destroys the evidence that §3's minting rule
   was violated upstream.
3. **Order the tables by dependency.** A table referenced by others syncs
   **first**, or the receiving host lands rows pointing at ids it has
   never seen. Pin the order with a test, not a tuple's order.
4. **A table without the sync columns is not synced**, wherever it lives.
   Moving state into Postgres is step one of two; a table in the right
   database with no sync columns is still per-host, and now *looks*
   fleet-wide — worse than the sidecar it replaced.

## §6. The pairing — what goes where

| | goes in | why |
|---|---|---|
| **state** | the 55432 database | it changes, needs provenance, must converge |
| **design** | files, under git | it is reviewed, versioned, diffable |

The dividing question is not "is it important?" but **"does it change
without a human deciding it changed?"** If yes, it is state. A spec is a
promise; a row is a measurement. A promise in the database is
unreviewable; a measurement in git is a lie the moment reality moves.

## §7. Checklist for a leaf adopting this

- [ ] Store resolves through the package's own resolver; unresolvable raises.
- [ ] Ids derived per §3, never minted; `issuer` recorded.
- [ ] The §3.1 condition put to sac **as a question**, and its answer recorded.
- [ ] Observation fields identified and explicitly included or excluded from sync.
- [ ] Sync columns present on every table intended to be fleet-wide.
- [ ] Deletion is a tombstone; no physical `DELETE` in the sync path.
- [ ] Conflict resolution explicit; immutable-field disagreement refuses.
- [ ] Table sync order pinned by a test.
- [ ] ACL keyed on derived id, stored as rows, absence ≠ unreachable.

## What this document cannot tell you

It has not been executed end to end — the **present, correct, and inert**
failure: it exists, it is right, it changes nothing. The first leaf to
retrofit an existing table should record **what it hit that this document
did not predict**; that account belongs here as §8.
