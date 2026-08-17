---
description: |
  [TOPIC] Cross-host identity — what makes a row the SAME row on every host
  [DETAILS] Fleet-global identity over a per-host store; the derive-or-allocate rule; what to do when a system has NO intrinsic attribute (the branch the fleet is actually in); why an allocated id is not a cardinality guarantee; and the detector-vs-constraint near-miss that answers such questions wrongly.
tags: [scitex-dev-cross-host-identity]
---

# Cross-host identity

Companion to [26_state-store-contract.md](26_state-store-contract.md)
(the store itself — validity, ACL, sync, state-in-db / design-in-git).
This file covers the one question hard enough to need its own document:
**what makes a row on host A the SAME row as one on host B?**

## §1. Global identity over a per-host store

**Identity is fleet-global. The store is per-host. The row converges by
sync.** No tension, once you separate a registry's two jobs: *naming* the
entity ("who is `scitex-dev`") is fleet-global; recording what THIS host
knows about it (last seen, port, host@name) is per-host. "Fleet-global"
must mean **every host converges on the same row** — not "one row lives
somewhere authoritative", which would make a local identity lookup depend
on a remote host being up, exactly the dependency a per-host store exists
to avoid.

**The test that separates the designs.** Partition hosts A and B, both
knowing `scitex-dev`. Do they agree on its id? Sound identity → yes, the
id was derived or allocated once. Per-host minting → no, and the
divergence stays silent until they try to merge.

## §2. The rule — derive it, or allocate it

> **A cross-host key must be stable under RELOCATION and unrecomputable
> at the POINT OF USE.**

Two ways to satisfy it, in order of preference:

```
DERIVE    from an intrinsic attribute, where one exists:
          deterministic_user_id(issuer="<oidc issuer>", subject="<oidc subject>")
ALLOCATE  once, at the authority that CREATES the entity; the entity
          CARRIES it thereafter, in its spec (a file, under git)
```

The defect to avoid is not assignment. A passport number is not derived
from the person and is still sound, because one authority issues it once
and the person carries it. What makes a key unsafe is being **re-derived
or re-assigned at each point of use** — a *mint as local inference* —
which diverges under partition with no way to tell afterwards which of
two ids was real.

So any key containing a hostname, an `AUTOINCREMENT`, or a first-seen
timestamp fails. **A UUIDv7 fails too, and less obviously**: it encodes
*when*, and it is minted per *instance* rather than per entity. Measured
2026-08-17 on the agent registry: **every restart mints a new one — 24
rows, 24 ids, one agent.** So the "identity" changes not merely on
relocation but on every restart, and a reviewer waves it through because
"uuid, globally unique, no host in it" reads as correct.

## §3. When there is no intrinsic attribute — the branch that matters

**The fleet is in this branch.** Measured 2026-08-17: agent names are not
fleet-unique, and cannot be.

The structural argument settles it before any code is read:

> A per-host store cannot enforce cross-host uniqueness at registration,
> because at the moment host B registers it has never seen host A's
> database.

Empirically, four names existed on more than one host in a *single*
host's DB — a **lower bound**, nobody having looked at the others — and
one pair overlapped for ~8.5 hours, cleaned up by a hand-typed note.
That is the tell: a human caught it, not a constraint.

When a system has no intrinsic attribute, **do not pick the least-bad
mint. Create the attribute**: allocate once, at creation, carried in the
entity's spec. That puts allocation in *design* and observation in
*state*, as the store contract requires — and names the usual root cause:
identity was being read out of an OBSERVATION table, which structurally
cannot answer a fleet-global question. An argument against the table, not
against uniqueness.

## §4. An allocated id is not a cardinality guarantee

Allocation makes the key stable. It does **not** stop two live processes
claiming one identity — a copied spec carries a genuine id, and both
copies hold it legitimately. That is a different failure, and it has
already produced a real split-brain: two instances, one id, two stores,
neither seeing the other's writes. Three failures look alike and are not:

| | symptom | fix |
|---|---|---|
| identity instability | key changes on relocation | allocate in the spec |
| address collision | two live entities, one *name* | unique addressing |
| cardinality | two live processes, one *identity* | a **lease** |

They present identically as "two rows, one id", which is why evidence for
one reads as evidence for all three. The right to RUN as an identity is
**state**: held by one process at a time, acquired at start, renewed
while alive, refused to a second claimant. Who you *are* is design; who
is *you right now* is state.

**Take one token, not a handshake.** A mutual handshake deadlocks or
double-commits under partition. Operator, 2026-08-07: *two holders is
not a race to be detected, it is a state that cannot be expressed* —
which is this file's derive-or-allocate rule in the cardinality domain.

**A TTL alone assumes clocks agree.** A paused holder can wake believing
its lease is valid and write honestly with a token that *was* legitimate.
So the lease carries a **fence**: a monotonically increasing integer
bumped on every handoff, so the stale holder is locked out by arithmetic
rather than by trusting its clock. Same reason `revision` and not
`updated_at` orders a conflict (26 §3.1).

## §5. State the condition; do not assume it

Where a key depends on another system's guarantee, write the guarantee as
a testable sentence and put it to that system:

> "sac refuses to register two agents with the same name **across
> hosts**."

That one came back **FALSE, with proof** — which is why §3 exists.
*Unknown* would have been a finding too. Never write down a conclusion
whose condition nobody checked: a blocker phrased as a verdict can never
expire, while one phrased as its testable condition expires visibly.

### §5.1 The near-miss that answers wrongly

Beware the shape that looks like the guarantee and is not. A `PRIMARY
KEY` on a name, raising a conflict error whose message quotes a design
doc, reads as enforcement — but if the cross-host *sync* path inserts
with `INSERT OR IGNORE`, the conflicting row is silently dropped and
first writer wins.

> **That is a collision detector, not a constraint.** A detector reports;
> a constraint prevents.

It has a sibling, and they fail differently. A constraint can be
**bypassed on one path** (the `INSERT OR IGNORE` above), or a design can
be **wired to no path at all** — a lease documented as "makes two live
instances unrepresentable", pure and fully injectable, that nothing
calls. Both read as enforcement to anyone who greps. So ask two
questions, not one: **which paths does it cover?** and **what calls it?**

Grepping that docstring would have answered TRUE. When checking an
invariant, find the path that **writes**, not the path that documents —
and check every writing path; the one that matters is usually the one
added later.

Corollary for your own comments: a comment asserting an invariant is a
claim about an enforcement path, and must name it. "Names are globally
unique" is unfalsifiable prose. "Enforced by PRIMARY KEY on
`comms_nodes.name`; the sync path uses `INSERT OR IGNORE` and does NOT
enforce it" is checkable, and a future edit invalidates it visibly.

## §6. Observations are not identity

`host_at_name`, `last_seen` and (usually) a port are **per-host
observations**. They must not participate in the key, and each needs an
explicit sync decision — the same agent legitimately has a *different*
`host_at_name` on different hosts, so if such a field rides the sync,
every host keeps "correcting" every other, forever. Either move them to a
per-host observation table, or keep them and **exclude them from the
synced column set with a comment saying they are host-local by design**.
Silent flapping is the worst outcome: it looks like activity, not a
mistake.
