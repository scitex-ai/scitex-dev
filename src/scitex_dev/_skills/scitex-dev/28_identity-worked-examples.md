---
description: |
  [TOPIC] Worked examples — leaves that actually executed the store/identity contract
  [DETAILS] What each retrofit hit that the contract did NOT predict, and the method that found it: ask-don't-grep, structural-before-code, capability probes over version checks, and reading source rather than summaries. One entry per leaf; append, never rewrite.
tags: [scitex-dev-identity-worked-examples]
---

# Worked examples — the contract, executed

Companion to [26_state-store-contract.md](26_state-store-contract.md) and
[27_cross-host-identity.md](27_cross-host-identity.md).

Those two state rules. This file records what happened when a leaf
actually applied them — specifically **what the contract did not
predict**, because a contract nobody has executed is *present, correct,
and inert*: it exists, it is right, and it changes nothing.

**Append entries; do not rewrite them.** An entry that gets tidied into
agreement with the current rules stops being evidence. If an entry drove
a change to 26 or 27, say so in the entry and leave the original finding
standing.

## Reading these entries: agreement is not automatically evidence

Several entries will report two parties reaching the same conclusion.
That is worth something **only if the two arrivals were independent**,
and independence is a property to check, not one to infer from the
parties being distinct.

Measured counter-case, 2026-08-17: one agent's claim about a service port
came from matching **stale comments**; it agreed with another agent's
genuinely correct card about a different thing. The agreement was real
and told them nothing, because both readings traced upstream to one
artifact. In a fleet whose agents talk this much, shared sources are the
common case rather than the exception.

> **Before counting an agreement as corroboration, name each party's
> SOURCE.** If they trace to the same artifact, it is one observation
> reported twice.

The positive control, from the same day: the tombstone rule was reached
independently from the sync mechanics (*a physical delete cannot
propagate, it can only fail to*) and from a foreign key noticed while
writing an unrelated table. Different artifacts, neither party having
seen the other's reasoning. **That** is what made it evidence — not that
there were two people.

It is this file's own subject in the social layer: **corroboration that
cannot fail is not corroboration.** Two readers of one source will always
agree, so their agreement could not have come out otherwise — the
instrument that never returns the unexpected answer.

---

## 2026-08-17 — scitex-cards, retrofitting `users`

**What the contract missed.** It covered how to *derive* a key from an
intrinsic attribute and said nothing about a system that **has none** —
which is the case the fleet is in. Not a broken rule; a missing branch.
It became 27 §3, and the rule was restated from "derive from what the
entity is" to "**stable under relocation and unrecomputable at the point
of use** — derive, or allocate once and carry it."

**The evidence chain, in the order it ran — worth copying as a method:**

1. **Ask, do not grep.** The key rested on another package's guarantee,
   so it went to that package as a testable sentence, with "unknown"
   named in advance as an acceptable answer. **This was the cheapest
   correct move.** Searching the codebase would have found the docstring
   in step 5 and built on it.
2. **Structural, and it settles the question alone.** A per-host store
   cannot enforce cross-host uniqueness at registration, because at the
   moment host B registers it has never seen host A's database.
   **An architectural impossibility outranks any amount of code reading**
   and cannot be invalidated by a later patch.
3. **Code.** No `UNIQUE`; only a non-unique host-qualified index;
   registration a bare `INSERT`.
4. **Empirical.** Two hosts, one name, ~8.5 hours, ended by a hand-typed
   `exit_reason` — a human was the constraint. Four duplicate names in
   *one* host's DB, and that is a **lower bound**: nobody looked at the
   others.
5. **The near-miss.** A different table *did* have `name TEXT PRIMARY
   KEY` and *did* raise a conflict error quoting a design doc — while the
   cross-host sync path used `INSERT OR IGNORE`, silently dropping the
   conflict. Grepping that docstring would have answered TRUE. See
   27 §5.1.

**The line worth memorising**, on why a "globally unique" uuid still
failed as an identity key:

> Uniqueness is a property of the VALUE SET; identity is a property of
> the BINDING.

**Gate a block with a capability probe, not a version check.** The
retrofit is held by non-strict xfail tests, each carrying its unblock
condition in its own reason string, so they flip to XPASS the moment the
dependency lands — no edit, no human re-reading a card. The probe is an
import plus a `callable()` check, deliberately not a version comparison:
**a release can ship the NAME without the BEHAVIOUR**, which is step 5's
defect in another costume. A probe goes true only when the thing exists,
from whatever direction it arrives.

That is "record the condition, not the conclusion" made mechanical. A
blocked card is a conclusion a human must revisit; a red test naming its
own unblock condition revisits itself.

**Read source, not summaries.** The first ruling in this thread allocated
the uid in the spec *"because the spec travels with the agent"* — until
forwarded **verbatim** text revealed that a spec also travels by being
COPIED, producing two agents under one identity with no error, which had
already caused a split-brain. That correction split the three failures
now tabulated in 27 §4. A summary would have preserved the ruling and
dropped the sentence that broke it.

**And a second correction, from the same thread.** The merge policy first
sent was *last-writer-wins by `updated_at`*. That is not "newest wins" —
it is **"fastest clock wins"**, and it was corrected to order on
`revision`. See 26 §3.1. The author of the rule reached for the
timestamp field within an hour of writing the rule, which is the
strongest argument for naming the ordering column explicitly in the
schema rather than trusting a reader to infer it.
