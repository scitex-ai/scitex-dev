# ADR-0006 — One store per host, consumed as a primitive

**Status:** Accepted (operator ruling, 2026-08-09)
**Owner:** scitex-dev, as DB primitive provider
**Consumers today:** scitex-cards, scitex-agent-container
**Consumers next:** scitex-writer, figrecipe, scitex-scholar — via scitex-hub

## Why this exists

To make the rules explicit. Rules organise things smoothly and make behaviour
predictable; a convention that lives in a chat thread does neither, because
the next package to adopt it reads code and docs, not scrollback.

Four instructions from the operator on 2026-08-09 combine into one design,
and they are quoted rather than paraphrased so nobody has to reconstruct
intent later:

> "db (sqlite3 or postgres) for a host and synchronized across hosts"

> "this will enable to work researchers collaboratively without laborious
> computational setups"

> "to keep consistency, you must provide primitive and allow leaf packages to
> consume your logic in a ssot manner"

> "we must normalize the use of db across leaf packages, hosts to keep things
> coordinated with low risk of corruption"

## The problem, measured

A single leaf package kept its data in four-plus places at once. Counted in
`scitex-cards/src/**/*.py` on 2026-08-09:

| Location | References |
|---|---|
| `sidecar` | 237 |
| `inboxes` | 142 |
| `threads.json` | 37 |
| `runtime_dir` | 26 |
| `todo.db` | 20 |

plus the PostgreSQL card store itself. Cards in Postgres, DM threads in a
JSON sidecar, notifications in a SQLite file, inboxes in another section.

**The user-visible consequence:** the operator's direct messages reached
nobody, all day. A DM committed to one store while its notification was
written to another, so the write reported success and no agent was ever
woken. Success in one store is silent about the other. That is not a bug in
any one function — it is what happens when there is no primitive to consume.

A second consequence, same root: the notification sidecar is located *from
the store path*, so when the store became a DSN the sidecar could not follow
it. The laptop wrote its own file; compute-04 read a different one; no path
between them existed.

## Decision

### 1. One store per host, holding every record kind
Cards, DMs, notifications, inboxes, reactions, receipts — all are RECORDS
with a schema. No category of product data gets its own file. A leaf that
needs a new kind declares a `Schema`; it does not open a path.

### 2. SQLite by default, and the default is genuinely zero-config
No daemon, no port, no credentials, no network. A laptop with no
connectivity is a fully working node.

This follows from the product intent, not from benchmarks. If the answer to
"how do I start?" contains the word "Postgres", the product has failed the
researcher it was built for. No performance argument overturns that.

### 3. Postgres is a per-node upgrade, never a prerequisite
For a node with many concurrent local writers, or a dataset outgrowing a
file. The choice is invisible to callers — the dialect layer owns parameter
style, quoting, types and upsert syntax. A collaborator on SQLite and a lab
on Postgres must be able to sync with each other, which falls out of an
engine-independent oplog.

**Postgres gives multi-CLIENT, not multi-NODE.** One server with many remote
clients is still one node. Per-host writable Postgres replicas that reconcile
are *harder* than SQLite, not easier — logical replication plus conflict
resolution, or an extension. What provides multi-node is the replication
layer, not the engine.

### 4. Hosts synchronise by directed replay; nothing is central
Peers replay each other's ordered oplogs under a `first_seq == cursor + 1`
assertion. Never set-difference. Conflicts resolve by hybrid logical clock.
Nothing is ever deleted — hide-flag only.

A severed host keeps accepting reads and writes. No coordinator, no quorum,
no primary. Losing a peer costs currency, not availability.

Collaboration is therefore **peers syncing**, not shared access to one
server. Nobody hosts anything for anybody; nobody's laptop is anybody else's
dependency.

### 5. SSoT means one implementation, not one convention
Leaves consume `scitex_dev.store`. They do not re-implement it to a
documented spec. A convention that each package implements separately is
exactly how four storage locations appeared while everyone believed they were
consistent.

### 6. No path-derived side stores
Anything deriving a filesystem location from the store target is the defect,
not a workaround for it. `PostgresDsn.__fspath__` raises for this reason.

## Consequences

**The completeness bar changes.** It is not "can the primitive store cards"
but "is there anything a leaf still has to persist outside it". Every
uncovered case is a future split-brain, because a sidecar exists precisely
where the primitive did not reach.

**Low corruption risk is a design constraint, not an aspiration.** Concretely:
one write path (no dual-write toggle), an optimistic lock with a required
`expected_revision`, no delete verb, and a contiguity assertion that refuses
a gapped replay rather than applying it.

**Order matters.** This must land before the spread to scitex-writer,
figrecipe and scitex-scholar. Five more consumers copying the sidecar shape
multiplies the migration by five, in namespaces scitex-dev does not own.

**Scope limit, so this is not read as bigger than it is.** The primitive owns
STORAGE, REPLICATION and the plumbing of record kinds. What a card means,
what a DM means, stays with the leaf package.

## Naming

`todo` is retired in every form — `scitex-todo`, `SCITEX_TODO_*`,
`runtime/todo.db`. The package is `cards`. Operator, 2026-08-09: "never use
scitex 'todo' in any forms ... I DO NOT WANT TO SEE SUCH LEGACY AND BUGGY
LITERAL".

Measured blast radius: **605 files across 11 repos** (excluding a stale
duplicate checkout at `~/proj/scitex-todo`, which is `scitex-cards.git`
cloned twice and six days behind — it doubled every fleet-wide count
symmetrically, so nothing looked wrong).

`runtime/todo.db` also violates this repo's own convention
(`01_ecosystem/13_runtime-state-db-layout.md`: `<pkg-short>/runtime/<pkg-short>.db`),
inside a directory that was already correctly renamed. A half-finished
migration is the worst state: both names are live and neither looks wrong.

`SCITEX_TODO_AGENT_ID` is injected into every container by
scitex-agent-container at launch, so renaming readers without renaming the
injector strands every agent's identity. That one is a coordinated change
across scitex-dev, sac and scitex-cards.

## Related

- `dev-db-primitive-owns-inbox-rail-and-cards-not-todo-naming-20260809`
- `cards-inbox-rail-must-live-in-postgres-drop-todo-db-20260802` (scitex-cards)
- scitex-cards ADR-0016 — the three board wipes of 2026-07-19/21, and the
  ruling "No code may delete a row because it is absent from another store"
- `01_ecosystem/13_runtime-state-db-layout.md`
