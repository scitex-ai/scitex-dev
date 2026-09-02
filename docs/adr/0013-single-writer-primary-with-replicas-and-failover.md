# ADR-0013 — A single writer, replicas, and failover

**Status:** Accepted (operator ruling, 2026-08-25)
**Supersedes:** ADR-0006 (one store per host, consumed as a primitive)
**Owner:** scitex-dev, as DB primitive provider
**Consumers:** scitex-cards, scitex-agent-container

## Why this exists

ADR-0006 forbade exactly the topology this one adopts. That reversal is the
operator's, it is deliberate, and it is recorded here so the next reader does
not rediscover the old ruling and re-derive the old design. A superseded ADR
left standing as "Accepted" is not neutral: on 2026-08-25 an agent spent a
morning designing toward the shape ADR-0006 exists to prevent, flagged the
conflict, and then drifted back into it anyway.

The operator's words, quoted rather than paraphrased:

> "昔私が書いた ADR ですけど、それはもう古くて。今は単一のライター、1つだけ
> ライターでプライマリーにして、後はレプリカにする。でフェイルオーバーで
> 単一障害を防ぐという方向に舵を取りました。"

## Decision

### 1. One writer. Everything else is a replica.
Exactly one node accepts writes at any moment. Every other node carries a
read-only replica. This is the reversal: ADR-0006 §3 said "NO CENTRAL SERVER
— one Postgres per host, synchronised by oplog", and that is no longer the
design.

### 2. The single point of failure is answered by failover, not by dispersion
ADR-0006's argument against centralisation was the 2026-08-09 outage: the
fleet's only Postgres lived on a laptop, the laptop rebooted, and every agent
lost the board at once. That failure mode is real and is not disputed here.
The answer is now promotion of a standby rather than giving every host its
own writable store.

### 3. Promotion requires a quorum. A partitioned node must NOT promote itself.
"I cannot reach the writer" and "the writer is gone" are indistinguishable
from a single vantage point. A node that promotes itself on local evidence
produces two writers, both accepting writes, whose histories cannot be
reconciled afterwards. Promotion therefore requires a majority to agree the
writer is gone; a partitioned minority stays read-only and refuses writes.

This is a real cost and it is accepted knowingly: a severed host's agents
stall. ADR-0006 §4 chose the opposite trade ("a severed host keeps accepting
reads and writes"), and that is the substance of the reversal.

### 4. Intermittent nodes are the documented exception
A machine that regularly leaves the network — the operator's laptop is the
standing example — does not participate as a replica of the single writer.
It keeps a local store and reconciles on reconnect, accepting staleness in
exchange for continuing to work while away.

This is not split-brain: the laptop never claims to be the writer. Its
records are new rows under its own origin, so reconciliation is an append,
not a contested overwrite. That property depends on identifiers being
partitioned by origin, which the `(origin, seq)` oplog key already provides.

### 5. Conflict resolution: leaves declare, the writer executes
Resolution policy is domain knowledge and does not belong in the database.
Leaf packages declare their rules; the primitive supplies the mechanism. The
rules are then executed at one place — the writer — so that one input cannot
produce two answers.

Two conditions follow:

- **Resolution must be deterministic.** Same inputs, same result, or nodes
  diverge permanently rather than converging.
- **A promotion target must carry the same resolver versions as the writer
  it replaces.** Promoting to a node with different plugin versions silently
  changes the answers. Version match is a precondition of promotion, not a
  cleanup afterwards.

### 6. Nothing names the writer's address directly
Connection targets name a *service*, not a host. Moving the writer — planned
relocation or failover — changes one line per host, not a DSN embedded in
every spec. As measured on 2026-08-25, the fleet had the writer's address
hardcoded in 95 spec files plus `config.yaml`, on each host; under that shape
failover is unusable in practice because performing it means editing several
hundred files.

### 7. The legacy shared role is retired
A single shared login shared by every principal is incompatible with knowing
who did what. Principals authenticate as themselves. The role named after one
database is a leftover from when the cluster held only that database, and it
carries no privileges.

## What ADR-0006 still gets right

Not all of ADR-0006 is superseded, and the parts that survive are load-bearing:

- **§1 one store per host holding every record kind.** The 2026-08-09 DM
  incident — writes committing to one store while notifications went to
  another — was caused by product data scattered across files, and that
  diagnosis stands.
- **§5 SSoT means one implementation, not one convention.** Leaves consume
  `scitex_dev.store` rather than reimplementing it.
- **The reasoning for PostgreSQL over SQLite**, in particular that SQLite has
  no concept of *who*. This ADR strengthens that argument rather than
  weakening it.

Only §2's "per host", §3, and §4 are reversed.

## What this ADR does NOT yet change

This document records a decision; the implementation still describes the old
one. As of 2026-08-25 the following state the superseded design as current,
and they are accurate about the code *as it stands today* — the fleet has not
been converted:

| Location | What it asserts |
|---|---|
| `src/scitex_dev/store/_host.py` (module docstring, and the note at ~L33) | "one Postgres PER HOST. It does not mean one [central server]" |
| `tests/scitex_dev/store/test__replication.py` (~L11) | "no coordinator, no quorum, no lock server and no 'primary'" |
| `src/scitex_dev/status/_ledger.py` (~L19), `src/scitex_dev/status/spec/status-codes.md` (~L275) | "one store per host, oplog-based directed replay" |
| `docs/adr/0011` (~L333) | cites ADR-0006 "D3 no central" |

They are deliberately left alone. Rewriting them now would make the code
describe an architecture that does not exist yet, which is worse than a
docstring that honestly describes today. They change when the behaviour
changes, not before.

Citations of ADR-0006 elsewhere mostly point at Decision 5 ("leaves consume
the primitive") or the SQLite ban. Both survive, so those references remain
correct and need no edit.

Note for searchers: `scitex-agent-container` has its own, unrelated ADR-0006
about `to_home` materialisation layout. References to "ADR-0006" in that repo
are not about this topic.
