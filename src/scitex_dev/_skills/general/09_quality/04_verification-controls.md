---
description: |
  [TOPIC] Verification Controls — when the control itself licenses nothing
  [DETAILS] The failure modes of the checks prescribed by the claim-type rules: controls that are vacuous (cannot fail), inert (present but disarmed), mispositioned (never reach what is under test), or sampled wrong (one Bash call is one sample). Plus degrade branches where a hard failure hides and the symmetric relabel trap when repairing one, the status words (`skipped`, `masked`, `0`) that fuse a failed measurement into a clean one, and why a commissioned finding must land as a card. Use before trusting a green, a control, or a summary line.
tags: [scitex-general-quality-verification-controls]
---

# Verification Controls and Follow-Through

Companion to [03_verification-doctrine.md](03_verification-doctrine.md), which
gives the rule per claim type. Same underlying shape:

> **A failed measurement rendered as a confident value.**

There the failure is in the measurement. Here it is one layer out — in the
**control** that was supposed to catch it, in the branch that swallowed it, in
the word the summary printed, or in what happened to the finding afterwards.

## 7. Controls that license nothing

**Vacuous — the control cannot fail.** Run the known-bad case in the same
batch. If it passes too, throw the result away. Instance: 20/20 for two
workarounds *and* 20/20 for the known-broken form — one sentence away from
"workarounds verified", when nothing in that run could have failed.

**Inert — the control exists but is disarmed.** More dangerous than a missing
one: a missing guard gets built, a present-but-inert one closes the ticket and
is then cited as coverage. One day's instances: a CI recovery path behind an
unset variable; a health gate that read *absence* as green; a cleaner scoped to
a directory not containing the bloat, printing `removed=0 kept=235` — what a
clean tree prints. Never accept "there is a check for that" — ask when it last
fired and what it did. Worst measured case: `audit-project` printed `SUCC` over
53 live findings, its summary counting errors only. So a CLI-driven mutation
proof **cannot fail** while the rule under test sits at severity `W` — plant a
violation, the CLI still says SUCC. A week of such proofs is now treated as
UNPERFORMED, not passed.

**Mispositioned — the probe never reaches what is under test.** It reports *the
absence of the phenomenon* rather than its own blindness. Below the effect: an
engagement qualifier inside a shell script, where the effect operates on the
tool-call layer above it — NOT-ENGAGED on a container where an inline call
demonstrably engaged. Upstream of it: a pool health probe returned 403 in 16ms,
the ACL gate rejecting *before* the worker pool, so a fast rejection and a
healthy pool are one reading. The `SUCC` banner above is this at the reporting
layer — decided upstream of the finding count. Ask what a probe must traverse
to reach the failure you care about.

A scoped checker is mispositioned by construction when the scope does not
recurse. Measured 2026-07-23: `check_skill_dir` iterates one directory
(`iterdir`, not `rglob`), so aimed at `_skills/general/` it examined **1 leaf**
(`40_playground.md`) and never saw the 5 leaves under `09_quality/` at all. It
is not silent — it reported an unrelated `§3.index-monolith` on `general/`'s own
SKILL.md — and that is what makes it worse: a report about *some* file reads as
a report about *your* file. Two agents in a row took it as size coverage for
`09_quality/`. Aim a scoped checker at the directory that actually holds the
files, then prove the aim: the same run on `09_quality/` said CLEAN, and
inflating one leaf to 30080 B made `§4.monolith` fire — so the CLEAN was earned,
not structural.

**Sampling — the unit of variation is the Bash call.** Identical command text
gave one result 5/5 in one invocation and the opposite 20/20 in another, each
internally consistent. Every loop inside one call is **one** sample, not N.

## 8. Masking: where a hard failure hides, and how to fix it

**A degrade branch is where a hard failure goes to hide.** For every `except`
that degrades rather than fails, ask what would tell you it fired. Instance:
`try: import … except: warn` turned an `ImportError` into a log line.
`_resolve_runtime_self_identity` was extracted but never re-exported, three
callers still imported it from the old module, and both self-peer call sites
degraded to "continues without persisted self-peers" — persistence was OFF on
develop while the service reported normal operation.

TELL: a fallback whose only trace is a log line nothing asserts on.
CHECK: make the degraded path emit a value the caller's summary must carry, so
it surfaces where the result is read, not only where it happened.

Repairing one has a symmetric trap. A fix for "the cron reports 0 when it cannot
read" can be satisfied by relabelling every case UNKNOWN — green, and the
true-zero signal destroyed. The control arm — *readable and genuinely empty
STILL reports zero* — is what distinguishes the repair from the relabel.
Mutation-prove both arms.

## 9. Status words that fuse a failed measurement into a clean one

- **Skipped is not passed.** A CI summary read "8 passed" where one leg was
  `skipping`. Report the skipped state as its own state; never fold it into a
  pass count.
- **Green can be declared masking.** An audit went green with 150 violations
  masked by declared `skip_rules` (PS-139, PS-221): visible in the log, but
  `audit: SUCCESS` alone reads as clean. Distinguish *fixed* from *deferred*.
- A count that includes what it did not check is not a count.

## 10. Commissioned findings land as cards, not prose

A commissioned finding arrives as a **report**, not a **symptom** — a symptom
interrupts you, a report waits, so it is the easiest kind to shelve. Measured:
scitex-dev's own agent reported the cron read defect hours before a peer nearly
escalated a false fleet outage on it. This needs a mechanism, not resolve —
commissioned findings go into scitex-cards as cards, not a session transcript.
