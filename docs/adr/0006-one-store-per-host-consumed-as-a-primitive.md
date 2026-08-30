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

> **Read this together with Decision 3, which was reversed on 2026-08-30.**
> Every host still runs an instance, so this decision stands as written — but
> those instances are now READ-ONLY REPLICAS of one writable node on nas-03,
> not independent stores. "One instance per host" is a statement about where
> Postgres runs, no longer a claim that each host can be written to.

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

### 3. ONE CENTRAL NODE — nas-03 is the writable store for the fleet

**This decision was REVERSED on 2026-08-30.** It previously read "NO CENTRAL
SERVER — this is the condition on Decision 2", and argued that "Postgres by
default" must mean one Postgres per host synchronised by oplog, never one
Postgres that every host connects to. The reversal and its cause are recorded
here rather than in a second ADR, so a reader finds one answer instead of two
that disagree — the same treatment Decision 7 received on 2026-08-10.

#### What changed

The operator ruled, first as a standing principle on 2026-08-25 and again
explicitly on 2026-08-30:

> The centre should always be nas-03. […] nas-03 is the centre; the design has
> changed.
>
> — the operator (rendered in English; the original was spoken Japanese, which
>   by standing rule does not appear on public surfaces)

So the fleet runs **one writable PostgreSQL on nas-03**, and every other host
carries a read-only replica of that same cluster. Measured 2026-08-30, one
query against two targets:

    scitex-primary:55432   pg_is_in_recovery()=FALSE   100.64.0.5   sysid 7672112238472680366
    100.64.0.1:55432       pg_is_in_recovery()=TRUE    100.64.0.1   sysid 7672112238472680366

Identical `system_identifier` — one cluster, streaming replication, one primary.
`scitex-primary` resolves to 100.64.0.5, which is nas-03.

#### What now answers 2026-08-09, because the incident has not gone away

The superseded text was written against a real outage, and an honest reversal
has to say what replaces its protection rather than quietly drop the argument.
The outage: the fleet ran a single Postgres **on the operator's laptop**; the
laptop rebooted; every agent stayed alive and lost the board simultaneously.

The mitigation is the *choice of host*, which is precisely the operator's
stated reason for naming nas-03. **nas-03 is the always-on NAS.** Workstations
get rebooted, closed, and re-imaged; a store on one of them makes fleet
availability a function of whoever last used that desk. The 2026-08-09 failure
was not "a central node" in the abstract — it was a central node on a machine
nobody had agreed to keep running.

That is a narrower claim than the old text made, and it should be read
narrowly. Centralisation still costs what it always cost: if nas-03 is down or
unreachable, no agent can write. What changed is that the fleet now accepts
that cost knowingly, on a host chosen for uptime, instead of paying it by
accident on a laptop.

**Postgres still gives multi-CLIENT, not multi-NODE**, and that sentence from
the superseded text remains true — it is simply no longer an argument against
this design. One server with many remote clients is one node, and the fleet has
one node by intention.

### 4. Replicas are READ-ONLY, and only `pg_is_in_recovery()` can tell you

**Reversed 2026-08-30 alongside Decision 3.** This previously read "Hosts
synchronise by directed replay; nothing is central", and promised that "a
severed host keeps accepting reads and writes. No coordinator, no quorum, no
primary."

That promise is now false and its inverse is load-bearing: a severed host
accepts **no writes at all**, because its local node is in recovery. Losing the
centre costs availability, not merely currency.

**The trap this decision exists to name.** A replica of the same cluster shares
that cluster's `system_identifier`, and a board copied into it shares the
lineage uuid. So both halves of the store-identity pin answer *matches* against
a read-only standby, and an unpinned client cannot tell a stale replica from
the store it meant to reach. Measured 2026-08-29: identity pinned on both
halves reported `matches` / `may_proceed=True` against a 36-hour-stale replica.

`pg_is_in_recovery()` is the only field that discriminates — `True` on a
replica, `False` on the primary. It is a ROLE question, not a lineage question,
and nothing has to be kept in sync for it to stay true. For freshness rather
than role, compare `pg_last_xact_replay_timestamp()` against now; never use
identity for that.

Consequently the store's zero-config default resolves to the central node, not
to this host's socket, and refuses rather than degrading — see the resolution
order in `scitex_dev.store.host_store`. A default that lands on a local replica
does not fail at connect time; it fails on the first write, or serves stale
reads indefinitely, which is the silent wrong answer this ADR keeps cataloguing.

### 5. SSoT means one implementation, not one convention
Leaves consume `scitex_dev.store`. They do not re-implement it to a
documented spec. A convention that each package implements separately is
exactly how four storage locations appeared while everyone believed they were
consistent.

### 6. No path-derived side stores
Anything deriving a filesystem location from the store target is the defect,
not a workaround for it. `PostgresDsn.__fspath__` raises for this reason.

### 7. Connect over **TCP on 55432** with mandatory keys and a real ACL

**This decision was REVERSED on 2026-08-10.** It previously read "connect
over a UNIX socket; no TCP port by default". The reversal and its cause are
recorded here rather than in a second ADR, so a reader finds one answer
instead of two that disagree.

#### What changed, and why

The operator asked what the socket's weaknesses were. The honest answer
retired the decision:

> A socket gives us less freedom. Can we go with 55432 after all? File
> write permissions get complicated, and ACLs are awkward that way.
>
> External users connecting to the TCP endpoint on scitex.ai, agents at
> all sorts of different privilege levels connecting — especially external
> agents joining over A2A.
>
> — the operator, 2026-08-10 (rendered in English; the original was spoken
>   Japanese, which by standing rule does not appear on public surfaces)

**A UNIX socket cannot express WHO.** Its entire access-control vocabulary
is "can this process open this path" — one bit, carrying no identity beyond
uid. The requirement is per-agent, per-project, per-collaborator ACL plus
recorded authorship ("who wrote this"). The filesystem is the wrong layer for
that question; Postgres roles are the right one.

Decision 3 said hosts never connect to each other's Postgres, and that
still holds for HOST-TO-HOST replication. But it never covered the clients
the operator actually intends: external users, agents at differing
privilege levels, and A2A peers that may join. Those are not hosts
replicating; they are clients authenticating. The old text answered a
narrower question than the system was going to ask.

#### The decision

    postgresql://…@<host>:55432/scitex   TCP, TLS, per-identity role
    ~/.scitex/pg/                        PGDATA — bind-mounted OUTSIDE the
                                         container (Decision 8 ENFORCES this)

- **55432, never 5432.** Unchanged, and for the unchanged reason below.
- **External connections are permitted** — not merely localhost.
- **Keys/TLS are mandatory.** Operator-confirmed, 2026-08-10: "of course keys
  are required."
- **`scram-sha-256`. Never `trust`.**
- **Per-human and per-agent roles**, not one shared superuser.
- **Row-level ACL enforced IN THE DATABASE**, not in client code — a check
  that lives in the client is absent for every client that skips it.
- **Authorship as a column**, so "who wrote this" is queryable rather than
  reconstructed from logs.

Permitting external access is not the same as open access, and the
difference is the whole security posture. Reachability must never by itself
confer write permission.

#### What survives from the old decision

The reasoning that produced the socket recommendation was not wrong, and it
is retained: **5432 is refused.** On 2026-08-09, `127.0.0.1:5432` on
scitex-compute-04 looked like a local server and was in fact a tunnel to
the operator's laptop; nothing about the address said so. 5432 buys only
the ability to omit a port from a connection string, and costs a collision
with any system Postgres — and, as measured, the ability of an address to
lie about what it reaches. Pinning to 55432 keeps that protection without
the socket.

#### Sequencing constraint this imposes

Concurrency control today is an `fcntl.flock` on a host-local file. **A
remote TCP writer holds no descriptor on this host and is not serialized by
it at all.**

Therefore compare-and-set inside the database is a **precondition of opening
the port**, not a follow-up to it. Opening TCP first would take a
lost-update defect that currently requires two local writers and hand it to
every external client — multiplying a silent failure at exactly the moment
its blast radius grows.

### 8. PGDATA lives OUTSIDE the container, and the store ENFORCES it

Raised by the operator, 2026-08-10:

> Unless the database itself lives outside the container, the data cannot be
> recovered when the container is destroyed — so detect that state and raise
> an error.
>
> — the operator, 2026-08-10 (rendered in English; the original was spoken
>   Japanese, which by standing rule does not appear on public surfaces)

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

**It guards the instance THIS HOST MANAGES, whatever the transport.** The
principle is observability, not socket-versus-TCP: check durability exactly
when this process can actually see the storage in question. A DSN naming a
Postgres elsewhere is left alone, because checking OUR filesystem would say
nothing about ITS durability — the exact vantage-point error this decision
exists to prevent.

> **RESOLVED 2026-08-10 (PR #534).** This note previously warned that
> `require_durable_pgdata()` was wired to the SOCKET branch of `host_store()`
> and would stop firing once TCP became the default. **That warning was
> wrong**, and it is corrected here rather than deleted, because the reason it
> was wrong is the useful part.
>
> Reading the code found the call already on the FALLTHROUGH branch — "no
> explicit DSN, so this is the instance we manage" — before the return.
> Changing that branch's DSN from socket to TCP never removed the call. The
> guard was structurally safe the whole time.
>
> The real exposure was one level down and easy to miss: **the guard's input
> was named after a transport.** `require_durable_pgdata(socket_dir=...)` cost
> nothing while PGDATA and the socket dir were the same path, but once TCP is
> the default, `socket_dir` is precisely the parameter a later cleanup drops —
> taking the durability check's argument with it. The parameter is now
> `pgdata_dir`, which is what it always meant: PGDATA is where the data lives,
> the socket was one way to reach it.
>
> **A guard whose input is named after a transport disappears when the
> transport does.** Two tests pin the invariant rather than a comment — the
> load-bearing one calls `host_store()` and asserts the refusal, so it fails
> if a future transport change drops the call.
> See card `dev-adr0006-decision7-reverse-to-tcp-55432-with-acl-20260810`.

### 9. MULTI-WRITER per record — concurrent writers are the designed-for case

Added 2026-08-10. This ADR was silent on its concurrency model, and the
silence was not free: **two complete implementations were built against it,
each reading it a different way**, before anyone noticed they disagreed.

- `feat/store-oplog-replay` assumed SINGLE-writer-per-record — "no conflicts
  to detect, no Lamport or vector clocks to keep" — and raises
  `SingleWriterViolationError` when two origins touch one record.
- What shipped on `develop` assumes MULTI-writer: ops carry only changed
  fields, and `_policy.py` / `_merge.py` resolve per field (LWW, MAX,
  element-keyed APPEND, UNION) ordered by hybrid logical clock.

One design's normal case is the other's raised error. That is not a feature
gap that could be closed by porting; it is a fork.

#### The decision

**Multi-writer.** Concurrent writers to one record are expected and are
resolved per FIELD, never per row.

#### Why — the operator's reason, which is the load-bearing one

> Multi-writer is better — we don't know how busy it's going to get.
>
> — the operator, 2026-08-10 (rendered in English; the original was spoken
>   Japanese, which by standing rule does not appear on public surfaces)

Single-writer-per-record is not merely a simpler model; it is a **bet on
topology and load**. It buys its simplicity by assuming a property nothing
enforces. The fleet already has agents, a board, HTTP handlers and — after
Decision 7 — external TCP clients all writing the same records, and the
operator is explicitly unwilling to bet on how contended that becomes.

The decisive property is the FAILURE MODE when the bet is wrong. A
single-writer store meeting a second writer does not degrade; under
`(origin, seq)` causal ordering it either raises or silently picks a winner,
and "silently picks a winner" is the lost update this ADR already spent a
card on. Multi-writer costs an HLC and a merge policy per field, permanently,
and in exchange has no wrong-assumption state to enter.

#### What is retained from the rejected design

**Fencing.** `SupersededFenceError` — an op authored under a fence that has
since been superseded, so a DEMOTED writer's ops cannot replicate as
legitimate. This hazard is orthogonal to the conflict model: field-level
merge does not care whether the writer was still entitled to write. It ports
cleanly precisely because it does not rest on the single-writer assumption.

**Not retained: intent-based dedup** (`has_intent`). Under this model,
changed-fields-only UPSERT and element-keyed APPEND are idempotent by
construction, so a client retry converges without an idempotency key.
Recorded as a deliberate omission rather than an oversight — if a case
appears where retry is NOT idempotent, that case reopens this line.

#### The lesson this decision exists to prevent repeating

An ADR that omits its concurrency model does not read as incomplete. It reads
as finished, and two competent readers will fill the gap differently and
build. **State the model, not just the mechanism.**

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
