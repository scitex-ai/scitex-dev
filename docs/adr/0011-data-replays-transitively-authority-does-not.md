# ADR-0011 — Data replays transitively; authority does not

**Status:** Accepted (operator ruling, 2026-08-12)
**Owner:** scitex-dev, as DB primitive provider
**Amends:** ADR-0006 D9, by naming what the fence may and may not do
**Consumers today:** none — that is the finding, not an omission
**First consumer:** scitex-agent-container, then scitex-cards

## Why this exists

The operator asked a direct question — *are the per-host databases that
synchronise, and that `sac` and the cards consume, actually progressing?* —
and it deserves a direct answer before any design.

**The protocol is built and nothing calls it.** `scitex_dev.store` shipped in
0.47.0 with an oplog, a hybrid logical clock, per-origin cursors, directed
replay with a gapless assertion, field-level merge and a deterministic
adoption path. Not one line of production code in `scitex-agent-container`,
`scitex-cards`, `scitex-todo`, `scitex-db` or `scitex-storage` imports it.
**The gap is not construction; it is a wire and two callers.** And before
either is built, the applier has a defect that makes connecting it worse than
leaving it disconnected — which is what this ADR rules on.

## The state of play, measured

Read on 2026-08-12 against the installed 0.47.0, which is byte-identical to
`origin/develop` for every file quoted here except `_host.py` and `_merge.py`.

**What exists.** `Store` (`_store.py`) with an optimistic lock and no delete
verb; `PeerState` (`_peer_state.py`) carrying `changes_since`, `origins`,
`cursor`/`set_cursor`, `fence`/`set_fence`; `replay` / `pull` / `sync` /
`outstanding` (`_replication.py`); `assert_contiguous` and
`assert_not_superseded` (`_oplog.py`); `build_genesis` / `install_genesis` /
`verify_adoption` (`_adopt.py`); three-valued `discover_stores`
(`_discovery.py`). This is a real directed-replay protocol, not a sketch.

**What consumes it: nothing.** Zero imports and zero calls to
`changes_since` / `apply_remote` / `origins` / `pull` across all five repos,
in production code and in tests. Both places that genuinely need convergence
built a weaker substitute instead:

| Substitute | Where | What it does |
|---|---|---|
| `INSERT OR IGNORE` blob over ssh | sac `_state/state_db_export.py` | insert-only; a remote UPDATE can never land, and it cannot tell it lost one |
| end-state comparator | scitex-cards `GITIGNORED/cardsync-transplant/` | untracked, out of package; its own docstring says *"When scitex-cards adopts the primitive, delete this."* |

That second one records the cost: **2,341 differing rows on 2026-08-10,
closed by hand.**

**Why nobody knew.** The `scitex-dev` checkout on this host is **89 commits
behind `origin/develop`** and has no `src/scitex_dev/store/` at all, while the
installed wheel is 0.47.0 and has it. "Merged" and "present in the tree you
are reading" are different facts, and this repository currently disagrees with
itself about which one holds.

## The eviction, measured

`assert_not_superseded` is a genuine addition: contiguity proves nothing was
missed, ordering proves what came first, and neither notices a writer that was
demoted, partitioned away or replaced and kept running. Under multi-writer the
hazard is sharper still, because field-level merge resolves who wrote LAST and
has no opinion on who was ALLOWED to.

The check is right. Where the fence came FROM was wrong. Four facts compose:

1. **Local writes carry no fence.** `Store._append` built its `OpEntry`
   without a `fence=`, so every op every store has ever written carries
   `FENCE_UNKNOWN` (0).
2. **Replay adopted the fence off the incoming entry:**

   ```python
   # _replication.py, replay(), before this ADR
   if entry.fence > store.fence(source):
       store.set_fence(source, entry.fence)
   ```

3. **`set_fence` refuses to descend** — correctly, since a fence a peer's own
   traffic could lower would defend against nothing.
4. **`assert_not_superseded` rejects any entry below the accepted fence.**

Compose them: one batch claiming `origin="B"` and any large fence sets
`fence(B)` on the receiver permanently. Every genuine op B goes on to write
carries 0, fails the check, and is rejected forever. **B is evicted, and it is
irreversible through the public API** — the only remedy was editing the cursor
table by hand, which is the class of repair this package exists to abolish.

Nothing in the layer authenticates the claim. `sync` iterates
`remote.origins()`, so the REMOTE decides which origins exist and what their
ops say. `assert_contiguous` verifies only that a batch is internally
consistent — that every entry's origin equals the `source` asked for — never
that the sender is entitled to speak for it.

**No attacker is required.** `build_genesis` takes a `fence` parameter and
`origin` is a free string, so an adoption minted under a host's name with a
fence set is enough to evict that host from every store the genesis is
installed into.

### The design sentence that produced it

`SupersededFenceError` stated the rationale plainly, and it is half right:

> The fence therefore lives in the log as a COLUMN of each op, not as a value
> held beside it: an op must carry the authority it was written under, or that
> authority does not survive replication to the node that has to judge it.

True of **judging** an op, false of **learning** the current fence. An op
carries its fence so a receiver can compare it against authority the receiver
already holds. Making it the SOURCE of that authority is what turned a check
into an instruction from whoever sent the batch.

### And the one comment that would have caught it said it was off

`assert_not_superseded`'s docstring read **"NOT YET WIRED INTO REPLAY …
nothing in the replication path invokes it, so it protects nothing"** — while
`replay` called it. The single place a reader would look to find out whether
the fence was live told them the mechanism was inert. That is recorded here
rather than quietly deleted: a comment describing a guard as switched off is
read as permission to stop reasoning about it.

## Decision

### 1. Data replays transitively; authority does not

Replay READS the fence to judge a batch and NEVER writes it. The adoption is
deleted. A batch can now only be accepted or rejected; it can never change who
is entitled.

Relaying a third party's ops stays legal and is a deliberate, tested feature —
safe because contiguity and field-level merge bound what a relayed op can do.
Neither bounds a fence, **because a fence is not merged, it is believed.** So
the two travel differently, and that asymmetry is the rule.

### 2. A fence moves only through an explicit administrative call

`set_fence` is the promotion verb and is called by something that
authenticated the peer — never as a side effect of accepting rows from it.
Nothing on the data path calls it.

### 3. `rescind_fence` exists, because "the fence only rises" is wrong as an absolute

Monotonic-up is right for the replication path and makes a mistaken fence
permanent, and a mistaken fence excludes a healthy host. `rescind_fence(source,
fence, *, reason)` performs the lowering and requires a non-empty reason.

The reason is **not persisted** — there is nowhere in this schema to put it,
and inventing a column to hold a string nobody reads would be worse than
saying so. It is required so the justification sits at the call site, where
review and `rg rescind_fence` both find it. That is the argument
`ANY_REVISION` already makes for being a named sentinel rather than a boolean.

### 4. A node writes under the authority it HOLDS

`_append` stamps `fence=self.fence(self.node)`. Judging peers by a fence while
stamping your own ops with "no authority at all" is a suicide pact: the first
real promotion anywhere makes every honest node's writes fail its peers'
checks. It remains 0 until somebody is promoted, so unfenced fleets are
unaffected.

### 5. `apply_remote` enforces the writer policy

Under `SINGLE_WRITER` the front door refuses a write to a record the actor
does not own; the replication path did not, so the rule was enforceable only
against callers who used the front door. A rule the front door enforces and
the back door does not is not a rule, it is a detour. `MULTI_WRITER` is
unchanged and pinned by tests at both poles — a check that fired there would
break the only consumer this primitive is designed for.

### 6. `apply_remote` still does NOT check the revision, and that is correct

This was reported alongside §5 as the same defect. It is not.
`expected_revision` is a compare-and-swap for a caller who READ a value and
wants to write it back. A replayed op is history that already happened
elsewhere; it never raced against the local revision, and rejecting it because
the local row moved on would break replay precisely when both sides wrote —
the only time replay matters. Concurrent edits are resolved by per-field HLC
merge, which is the mechanism for that job. **Adding the check would be a
regression, and it is declined explicitly so it is not "fixed" later.**

### 7. Host-to-host sync rides the existing SSH mesh

The transport question has an answer that costs nothing: **SSH, between hosts
that already reach each other with keys.** No new listener, no new port, no
new exposure, and no service to authenticate beyond what exists.

This is possible because **the remote side of the protocol is exactly two
methods.** `pull` calls `remote.changes_since(...)`; `sync` calls
`remote.origins()`; `outstanding` calls both. Nothing else on `remote` is
touched. So the wire is an adapter implementing two read-only methods, and
`_replication.py` needs no change at all to accept one:

```
local                                    peer (over the ssh mesh)
  sync(local, SshRemote(peer))  ──────▶  scitex-dev store serve-oplog
    .origins()                             → {origin: max_seq}
    .changes_since(origin, seq, limit)     → JSON lines of OpEntry
```

**The served verb is read-only.** It answers what the peer's log contains and
writes nothing, so a compromised or confused caller cannot use it to modify
the peer. All mutation happens locally, in `replay`, behind the assertions.

**What the applier checks about a peer that ssh has already authenticated:**
for DATA, nothing beyond the existing assertions — any authenticated peer may
relay any origin, by §1. For AUTHORITY, everything: a fence never arrives over
this wire at all, by §2. The authenticated identity gates promotion, and
promotion is not something a sync can perform.

### 8. This does not conflict with sac ADR-0024; it is a different rail

ADR-0024 mandates Cloudflare Tunnel with Cloudflare Access plus a mandatory
bearer, and forbids Postgres on the wire. That governs what must be reachable
from **outside** the fleet — the board's UI and status pages. Host-to-host
oplog sync is **inside** the fleet and rides SSH. Split by role; the two are
not exclusive.

Both agree on the load-bearing point, which is ADR-0024 D1 and ADR-0006 D3:
**Postgres is never published to another host.** Nothing here changes that.
Replication stays at the application layer, exchanging ops, exactly as
`_host.py` has claimed since it was written.

### 9. Order of work, and one consumer proven before the second

1. **This ADR's code change** — §1–§6. Local, no network, testable now.
2. **The SSH adapter** — §7. Two methods and a read-only server verb.
3. **sac as the first consumer, end to end.** Its state-db is SQLite, which
   the primitive speaks natively; it already has the mesh; and its current
   `INSERT OR IGNORE` export is a known-lossy substitute with a bounded
   replacement. One consumer proven whole beats two half-wired.
4. **scitex-cards second**, which is a larger job because it must also adopt
   (below).

A sync with no authorization that gains consumers is strictly worse than one
with no consumers, which is why §1 precedes step 2 rather than accompanying
it.

## What this does NOT do: the split that is hurting today

**This ADR prevents future divergence. It does not repair the existing
split, and the two are different jobs.** Repair is deliberately out of scope
and nothing here was reconciled, migrated or deleted.

Measured on this host on 2026-08-12, read-only:

| Store | What it is |
|---|---|
| `127.0.0.1:55432` | this host's own Postgres, `sysid 7672112238472680366`, PGDATA `~/.scitex/pg/18/main` — the ADR-0006 location |
| `127.0.0.1:5442` | a **different Postgres instance**, `sysid 7671108644284358700`, running in a container (`inet_server_addr 172.17.0.2`, PGDATA `/var/lib/postgresql/18/docker`), reached through a forwarded port. The retained dump labels it `nas_via_5442`; that it is the NAS is the dump's attribution, not measured here |
| `~/.scitex/cards/runtime/todo.db` | SQLite sidecar, still opened constantly, last written 2026-08-11 07:05 |
| `~/.scitex/cards/tasks.yaml` | absent now; its lockfile remains |
| `~/.scitex/cards/runtime/inboxes.json` | the notification inbox — a file sidecar located from the store PATH, so pointing the store at Postgres does not move it |

Two things follow that were not previously stated:

**They are two distinct database instances, not two views of one.** Their
`system_identifier`s differ, so the difference is physical and not a
configuration artefact. That is the per-host topology ADR-0006 asks for — with
no sync between them, and with `127.0.0.1` hiding which instance you are
addressing. It is the 2026-08-09 incident `_host.py` already documents (an
address that "looked like a local server and was in fact an SSH tunnel to a
laptop"), recurring under a new port number.

**The live divergence mechanism is process-local environment, not
replication.** The long-running MCP server resolves `SCITEX_CARDS_DB` to
`:5442`; a shell and a freshly-spawned CLI on the same host resolve to
`:55432`. Same package, same host, same store identity — two databases. The
retained 21:59 dump measures the result: **321 records only on 55432, 11 only
on 5442, 3,422 in both, 121 differing.** Both instances report the same
application `store_uuid`, so nothing in the store's own vocabulary can tell
them apart; only the physical `system_identifier` distinguishes them.

**Therefore the first repair step is not code.** It is making a host's store
target name the host and fail loudly on mismatch, so two processes cannot
disagree about which database they are on. Only then is adoption meaningful.

When repair does happen it must respect `_adopt.py`'s rule: genesis is built
**once** over a merged record set and the identical log installed everywhere.
`install_genesis` refuses a store that already holds rows it did not seed, so
the two divergent instances cannot each be adopted separately — and if they
were, each host's genesis would replay into the other and last-writer-wins
would overwrite real edits with snapshots. `verify_adoption` compares field by
field rather than by count, for the reason it records: on 2026-08-10 two card
stores both reported 3,707 rows while 7,646 bytes differed.

## Consequences

- One previously passing test asserted the eviction as a requirement
  (`test_replay_adopts_the_fence_it_accepted`). It is replaced by its
  inversion, and the replacement says why in its docstring. A test that pins a
  bug is worse than no test, because it converts the fix into a regression.
- Fencing is now inert until something calls `set_fence`. That is the correct
  resting state: no fence in the fleet is real today, and an authority nobody
  issues should exclude nobody.
- `SINGLE_WRITER` stores will begin refusing remote ops they used to accept.
  No such store exists in the fleet, so the blast radius today is zero — and a
  store that wanted them accepted wanted `MULTI_WRITER`.
- The eviction hazard is closed against accident as well as malice, which
  matters more: the genesis path could reach it with no attacker at all.
- An operator can now recover from a wrongly-recorded fence without raw SQL.

## Deliberately not here

- **Signatures or a MAC on oplog entries.** SSH authenticates the channel and
  the fleet is mutually trusting inside it. Per-entry cryptographic provenance
  is the answer to a threat model — untrusted relays — that this fleet does
  not yet have, and building it now would be the second unused protocol.
- **Binding `origin` to the authenticated channel identity.** It would break
  relay, which is a deliberate feature. §1 is what makes relay safe instead.
- **Persisting who rescinded a fence and why.** Named in §3 as a known
  omission with its reason, rather than solved by a column nobody reads.
- **Any repair of the divergent stores.** Separate job, stated above, with a
  prerequisite that is not code.
- **Moving the notification inbox into the card store.** Real, measured, and
  tracked elsewhere; it is a scitex-cards concern, not a primitive one.

## Unverified — recorded rather than rounded

- **The live divergence was not re-measured.** The 321/11/3,422/121 figures
  come from the retained 21:59 dump manifest, not from a fresh comparison.
  Other counts taken the same night by other tools disagree (3,494 via the
  card doctor; 3,491 vs 3,787 in sac ADR-0024), which is consistent with two
  stores drifting while being counted. Treat the SHAPE as established and any
  single number as a snapshot.
- **Whether `:5442` is the NAS.** Measured: it is a different instance, in a
  container, behind a forwarded port. The host it belongs to is the retained
  dump's label, not an observation from here.
- **`sac` as first consumer is a judgement, not a measurement.** It rests on
  its store being SQLite (which the primitive speaks natively), the mesh
  already existing, and its `INSERT OR IGNORE` substitute being known-lossy.
  No prototype has been built.

## Related

- ADR-0006 — one store per host, consumed as a primitive (D3 ONE CENTRAL NODE
  on nas-03, reversed 2026-08-30 — this reference previously read "no central
  server" and cited D3 as live support for that; D4 replicas are read-only and
  only `pg_is_in_recovery()` discriminates; D7 TCP 55432; D9 multi-writer)
- ADR-0016 (scitex-cards) — absence is not deletion; the three board wipes of
  2026-07-19/21
- sac ADR-0024 — card-database auth, two gates, not Postgres on the wire
- sac ADR-0015 — cross-host push, ssh transport
