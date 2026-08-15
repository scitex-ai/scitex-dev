# `scitex_dev.store` — the ecosystem's store primitive

One backend-agnostic store that every SciTeX package builds on. Not for
tidiness: each hand-rolled reconciler is another chance to re-derive the
same data-loss bug, and this fleet has already paid for that one.

## The two guarantees

**Nothing is ever deleted.** There is no delete verb. `Store.hide()` sets a
flag; the row, its history and every value it ever held stay readable via
`include_hidden=True` and in the oplog. A deep-delete may exist one day as
an explicit, named operation — never as the default and never implicit.

**Reconciliation is directed replay, never set-difference.** Two stores
converge by replaying each other's ordered operation logs under a hard
`first_seq == cursor + 1` assertion. A log says what *happened*, never what
*exists*, so absence from it is not evidence of anything.

That second guarantee has an incident behind it: **three board wipes on
2026-07-19/21**, one replacing **2,159 live rows** with a 5-row temporary
document. (2026-07-30 is the date of the ADR that analysed them, not of the
event — searching for 07-30 finds the postmortem and misses the wipes.)
The mechanism, per scitex-cards' ruling: *"reconciling two stores treated
as PEERS, where absence in one is interpreted as deletion in the other."*
The invariant that follows: **"No code may delete a row because it is
absent from another store."**

## Layout

| File | Responsibility |
|---|---|
| `_target.py` | `StoreTarget`, `Backend` — which store, where |
| `_discovery.py` | `discover_stores` — what exists on this host, three-valued |
| `_policy.py` | `FieldPolicy`, `Schema`, `MergeRule`, `WriterPolicy` |
| `_row.py` | `Row` — the record crossing the boundary |
| `_hlc.py` | `HybridLogicalClock`, `HLC` — the ordering authority |
| `_oplog.py` | `OpEntry`, `assert_contiguous` — the log and its gap check |
| `_merge.py` | per-field merge; decides what is *presented*, never what exists |
| `_apply.py` | the fold local writes and replay SHARE |
| `_guards.py` | record keys, the optimistic lock, ownership checks |
| `_store.py` | `Store` — the write door and the read door |
| `_replication.py` | `replay`, `pull`, `sync`, `outstanding` |
| `_identity.py` | `StoreIdentity` — "you are me" vs "you descend from me" |
| `_identity_state.py` | the `Store.identity` plumbing: mint the lineage, ask the instance |
| `_divergence.py` | `detect_divergence` — a fork PROVEN from the logs, never from absence |
| `federation/` | leaves declare a store; scitex-dev owns the machinery |
| `_dialect/` | SQLite (default) and Postgres (advanced) |

## How a leaf adopts a store

A leaf declares WHAT it stores and how its fields merge; it never resolves
WHERE the store is. Register a provider under the entry-point group
`scitex_dev.store.plugins`:

```toml
[project.entry-points."scitex_dev.store.plugins"]
scitex-cards = "scitex_cards._store_plugin:provide"
```

```python
from scitex_dev.store import StorePlugin, Schema, WriterPolicy

def provide() -> list[StorePlugin]:
    return [StorePlugin(name="cards", pkg="cards", schema=Schema.build(...),
                        writer_policy=WriterPolicy.MULTI_WRITER,
                        provider="scitex-cards")]
```

`discover_store_plugins()` aggregates every installed declaration and
`resolve_target(plugin)` says where it lives. Resolution is centralised
because per-consumer resolution is exactly what let one host reach two
Postgres instances that both answered to one `store_uuid` on 2026-08-11 —
404 cards on one, 146 on the other, every operation reporting success.

scitex-dev is a leaf here too: its own store (the status exchange ledger)
is merged through an INTERNAL provider, never an entry point, so discovery
never walks this package's metadata to find this package.

## Two places with no default, on purpose

**`FieldPolicy` has no default.** Every field states `kind`, `role`,
`required`, `merge` and `indexed`, or schema construction raises. The
dangerous one is `merge`: last-writer-wins on a field that should never
change discards history without a word, and immutability on a field that
legitimately moves makes every update after the first vanish. Neither
failure raises anything; both surface days later as "the data is wrong".

**`expected_revision` has no default.** Every write states
`NEW_RECORD`, an `int`, or the explicit `ANY_REVISION`. A bare row-level
update still loses updates when two writers touch the same field, so the
optimistic lock is required rather than offered — an optional safety belt
is worn by whoever least needs it. `rg ANY_REVISION` lists every place the
fleet has accepted lost-update risk.

## Ownership is not the replication key

`origin` — the node that **accepted** a write — numbers the oplog and
drives replay. `owner` is a domain field, and under `MULTI_WRITER` anyone
may change it.

This distinction is load-bearing. In the fleet's first consumer the owner
field is routinely mutated by non-owners: `reassign_task` rewrites it, any
agent comments on any card, and the operator resolves blocked cards from a
different host than the assignee. Keying replication on ownership would
make the operator's first resolve-from-elsewhere an illegal write.

`WriterPolicy.SINGLE_WRITER` remains available for stores that do have a
natural, stable owner. Replay correctness does not depend on the choice.

## The lizard-tail rule

A host severed from every other host keeps working. There is no
coordinator, no quorum and no primary: each host owns a complete local
store and writes without consulting anyone. Replication is something a host
does *with* a peer when one is reachable, never something it needs
*permission from* a peer to do.

Severance therefore degrades exactly one thing — how current this host's
copy of other hosts' data is. Hosts join by replaying from zero and leave
by going quiet; neither needs ceremony, and a departed host's rows survive
its departure. See `tests/scitex_dev/store/test_lizard_tail_host_survives_alone.py`.

## Import cost is a promise that is checked

Depending on this makes `scitex-dev` a hard runtime dependency of every
leaf that stores anything. The condition scitex-cards set, and this module
honours: importing it must not drag in the linter, CI, jobs, release or
ecosystem machinery. `tests/scitex_dev/store/test_import_cost.py` imports
the store in a subprocess and asserts those are absent from `sys.modules`.

If that test fails, make the import lighter. Do not shorten the list — a
gate loosened until it passes is a deleted gate that everyone still
believes in.

## Quick start

```python
from scitex_dev.store import (
    FieldKind, FieldPolicy, FieldRole, MergeRule,
    NEW_RECORD, Schema, Store, StoreTarget, WriterPolicy,
)

schema = Schema.build("cards", {
    "id": FieldPolicy(
        kind=FieldKind.TEXT, role=FieldRole.IDENTITY,
        required=True, merge=MergeRule.IMMUTABLE, indexed=False,
    ),
    "status": FieldPolicy(
        kind=FieldKind.TEXT, role=FieldRole.DATA,
        required=True, merge=MergeRule.LAST_WRITER_WINS, indexed=True,
    ),
})

store = Store(
    StoreTarget.for_package("cards"),
    schema,
    node="scitex-compute-04",
    writer_policy=WriterPolicy.MULTI_WRITER,
)
store.put({"id": "c1", "status": "open"}, expected_revision=NEW_RECORD)

# Reconcile with a peer — one direction, inspected separately.
from scitex_dev.store import sync
for result in sync(store, peer_store):
    print(result.describe())
```

## Related

- `_skills/general/01_ecosystem/13_runtime-state-db-layout.md` — where a
  package's `.db` lives and why `runtime/` is the redirectable unit.
- scitex-cards ADR-0016 — the wipes, the mechanism and the ruling.
