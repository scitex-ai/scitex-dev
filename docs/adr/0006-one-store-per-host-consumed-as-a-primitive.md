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

### 2. PostgreSQL is the default engine — one instance PER HOST
Every host runs its own PostgreSQL. SQLite remains implemented behind the
dialect layer but is NOT recommended and is not the default.

**This reverses an earlier draft of this ADR, and the operator's argument is
why.** That draft made SQLite the default on a zero-setup argument. The
decisive counter, in his words:

> "What good is handing a collaborator a SQLite file?"

Handing someone a file is SHARING, not COLLABORATING. And the deeper point:
**SQLite has no concept of WHO.** Anyone who can open the file has every
permission. PostgreSQL has roles, and multi-user identity is not something
that can be retrofitted onto a file — it is a foundation or it is absent.
For a product whose purpose is people working together, that decides it.

The setup objection was also weaker than it looked. Shipping Postgres via
Apptainer removes the install burden, and the remaining operational work —
start on boot, restart on crash, upgrade, back up — is one-time tooling, not
a recurring human cost. In an agent-operated fleet that cost is paid once by
whoever writes the tooling.

`scitex-writer`, `figrecipe` and `scitex-scholar` should therefore expect
Postgres, not plan for a SQLite fallback.

### 3. NO CENTRAL SERVER — this is the condition on Decision 2
"Postgres by default" means **one Postgres per host, synchronised by oplog**.
It does NOT mean one Postgres that every host connects to.

This distinction is the whole lesson of 2026-08-09. The fleet ran a single
Postgres on the operator's laptop; the laptop rebooted; every agent stayed
alive and lost the board simultaneously. That outage was not caused by
Postgres — it was caused by centralisation, and choosing Postgres does
nothing to prevent a repeat.

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

### 7. Connect over a UNIX SOCKET; no TCP port by default
Because Decision 3 means hosts never connect to each other's Postgres —
they exchange oplogs at the application layer — each instance is only ever
reached from its own host. A TCP port is therefore unnecessary.

    ~/.scitex/pg/              PGDATA — the real data, bind-mounted OUTSIDE
                               the container so rebuilding it destroys nothing
    ~/.scitex/pg/.s.PGSQL      socket — no port

Three properties follow, and the third is the one that matters most: port
collisions become impossible; there is no ambiguity about which Postgres an
address refers to; and the instance is **not exposed to the network at all**,
so it cannot be reached accidentally from off-host.

That ambiguity was live on 2026-08-09: `127.0.0.1:5432` on scitex-compute-04
looked like a local server and was in fact a tunnel to the operator's laptop.
Nothing about the address said so.

**When TCP is genuinely wanted** (a GUI client, debugging), it is opt-in,
bound to `127.0.0.1` only, and uses **55432** — never 5432. 5432 buys only
the ability to omit the port from a connection string, and costs a collision
with any system Postgres. It confers no auto-start benefit: that comes from
the service manager, not the port number.

### 8. PGDATA lives OUTSIDE the container, and the store ENFORCES it

Raised by the operator, 2026-08-10:

> 「コンテナの外にデータベースの実態をおかないと、コンテナを壊したときに
>   データが復旧できなくなるので、そういった状態は検知してエラーを出す」

He was right that it was missing. Decision 2 *implied* durable storage and
`_host.py` carried a comment asserting PGDATA is bind-mounted outside any
container — but nothing verified it. **A comment states an intention and
cannot notice when the intention fails.**

The failure is specific and silent. `$HOME` is `/home/agent` inside these
containers while the durable bind lives under the host's home, so
`~/.scitex/pg` can resolve container-local. The store then comes up, works
perfectly, accepts every write, and loses all of it at the next image
rebuild — with no error at any point. Nothing in normal operation
distinguishes it from a correct deployment.

So `require_durable_pgdata()` runs on the socket branch of `host_store()`,
reads `/proc/self/mountinfo`, and **raises** when PGDATA lands on a
filesystem that does not survive a rebuild (`overlay`, `overlayfs`,
`fuse-overlayfs`, `tmpfs`). Measured on scitex-compute-04:

    /home/ywatanabe   ext4                  <- host bind, survives
    /                 fuse.fuse-overlayfs   <- container-local, does not

**It raises rather than warns.** A warning is what the four days of
undetected Telegram silence were made of — every check available was
advisory and every one reported healthy. A store that cannot keep what it
accepts must not accept it.

**It abstains when it cannot tell.** An unreadable mount table returns
without blocking: "cannot determine" is not "unsafe", and a guard that
fails every host with an unusual `/proc` would itself be the outage. This
is the same three-valued discipline the rest of this ADR runs on.

**It guards only the socket branch.** An explicit `SCITEX_STORE_DSN` may
name a Postgres elsewhere whose storage this process cannot observe, so
checking OUR filesystem would say nothing about ITS durability — the exact
vantage-point error this decision exists to prevent.

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

## What belongs in the store, and what stays a file

Recorded here because every adopting package will ask, and because getting
it wrong in either direction is expensive.

**The rule:** what a HUMAN EDITS is a file. What a PROGRAM queries, counts
and synchronises is a record in the store.

| Store | File |
|---|---|
| cards, DMs, notifications, agent state, run history, dependency edges | manuscripts, code, config, Markdown, LaTeX |
| you want to filter, count, know who changed it when, merge across hosts | you want `git diff`, review, a human editing it |

Quick tests when it is not obvious. Would you want to read it in a
`git diff`? File. Would you want `WHERE status = 'open'`? Store. Is it over
~1 MB, or binary? File.

**Large artefacts:** the bytes stay on disk; the store holds one row with the
PATH and a HASH. Never the blob itself. scitex-clew already works this way.

**The distinction that actually decides it — who resolves a conflict.** The
store merges automatically, field by field, ordered by hybrid logical clock.
A file merges through git, which means a person. So anything two hosts may
change at the same moment belongs in the store; anything a person writes
deliberately belongs in a file.

A manuscript makes it concrete: the text is a file, while "who owns this
manuscript and what state is it in" is a record. The content and the facts
about the content live in different places, and that is correct.

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
