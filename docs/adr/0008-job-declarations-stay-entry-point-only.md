# ADR-0008 — Job declarations stay entry-point-only; CRUD verbs act on code and on overlay, never on a second registry

**Status:** Accepted (2026-08-16) — operator ruling recorded below.
Proposed 2026-08-12; the ruling arrived on 2026-08-16 and is written here
because for four days "the correct form" was a decision nobody could cite.
**Owner:** scitex-dev, as owner of `JobSpec` and the `scitex_dev.jobs` entry-point group
**Consumers today:** scitex-agent-container, scitex-cards, scitex-dev's own `_ecosystem_jobs` provider
**Supersedes:** nothing. **Related:** ADR-0004 (unified JobSpec), ADR-0006 (one store per host)

## Context

`ecosystem dev <kind>` grew a group per `JobSpec` kind in PR #566. Reviewing that
surface for a "CRUD is missing" gap produced a finding worth recording before any
verb is added.

**The verbs that exist already cover the whole materialisation lifecycle.** Across
`dev service`, `dev timer`, `dev cron` and the deprecated `dev systemd` the full
set is `list`, `status`, `install`, `uninstall`, `start`, `stop`, `restart`,
`enable`, `disable`, `exec`. Every one of them operates on the MATERIALISATION of
a declaration — unit files, crontab lines, running units. **None creates, edits or
deletes a declaration.** So the gap is real, but it is narrower than "CRUD is
missing": what is absent is create / update / delete of *declarations*.

**Declarations are code.** A package declares jobs by publishing an entry point in
the group `scitex_dev.jobs` that loads to a zero-argument callable returning
`list[JobSpec]`. `discover_jobs()` merges three sources — the internal
`_builtin_jobs()` adapter over `_cli.cron._jobs.JOB_REGISTRY`, every entry point in
the group, and a test-only `extra_providers` seam.

Three measured properties make a second declaration source hazardous:

| Property | Where | Why it matters here |
|---|---|---|
| De-dup by `name`, **first provider wins**, duplicate dropped with a warning | `jobs/__init__.py` `discover_jobs()` | A second source that names an existing job is silently shadowed in provider order. Order is not a contract. |
| Naming/description/kind rules (PS-226…PS-229) are enforced by **static AST over `JobSpec(...)` call sites** | `_cli/audit/_project/_check_job_naming.py` | A declaration that is not a Python literal is **invisible to the auditor**. Every job declared in a data tier would silently escape enforcement. |
| The existing registry is deliberately code, not data | `_cli/cron/_jobs.py` docstring: *"The registry is intentionally a module-level dict (no YAML loader, no dynamic discovery): one diff, one commit, one PR."* | The position is already recorded. Reversing it needs a reason stronger than convenience. |

The fleet has already paid for ambiguous provenance in this exact shape. On
2026-08-09 a duplicated `dist-info` made `importlib.metadata` choose an entry-point
set **by readdir order**, and a `scitex_dev-0.42.0.dist-info` advertised a plugin
module that did not exist in the code on disk. Two claims about what exists, one
winner picked non-deterministically, no error. A second declaration tier is the
same failure with a nicer syntax.

## Decision

**1. `scitex_dev.jobs` entry points remain the SOLE source of job declarations.**
No `create` / `update` / `delete` verb will introduce a competing registry — not
YAML, not TOML, not a table. There is exactly one answer to "what jobs exist": the
installed code.

**2. `create` is spelled `scaffold`, and it writes SOURCE.**
`ecosystem dev <kind> scaffold <name>` generates a provider stub in the owning
package (a `JobSpec(...)` literal in a `_jobs_plugin.py`) plus the
`[project.entry-points."scitex_dev.jobs"]` line, then reports that the package must
be reinstalled for `importlib.metadata` to see it. This creates a declaration by
creating code, so the single-source rule holds, the AST auditor sees the new job
like any other, and the change arrives as one diff, one commit, one PR.

**3. `update` and `delete` of a declaration are REFUSED, loudly, with the correct
verb named.** For a job declared in installed code, "delete" is incoherent: the
declaration is a fact about what is installed, and the only way to remove it is to
change or uninstall the package. What an operator actually wants is already
spelled twice and correctly — `uninstall` removes the unit or crontab line;
`disable` stops it firing while leaving it declared. The refusal must say which of
those two was meant rather than silently doing one of them.

**4. Per-host operational OVERRIDE is a separate concept from declaration, and is
the only thing a mutating verb may write.** An overlay may adjust `enabled` and
`schedule` for a job **that a provider already declares**; it may never invent one.
Precedence is therefore not a contest: the declaration supplies existence and
identity, the overlay supplies per-host operational state, and the two cannot
disagree about what exists.

**5. An overlay row naming an unknown job is a LOUD, fail-closed error at load** —
not a skip, not a warning. A silently-ignored override is indistinguishable from
one that worked, which is the failure this ADR exists to prevent. `list` gains an
origin column so the effective value and its source are read together.

**6. Overlay storage is the per-host Postgres store** (`scitex_dev.store`, TCP
55432, ADR-0006). Not sqlite — banned for SciTeX state. Because these rows will be
synchronised between per-host instances, the table carries `origin_node`,
`row_uuid`, `revision`, `updated_at` and `deleted_at` **from creation**;
retrofitting them is a rewrite. Conflict resolution is per field class and never a
wall clock, and blind `ON CONFLICT DO UPDATE` is prohibited.

## Ruling

Recorded 2026-08-16. The operator referred to this ADR as settled and asked
that the packages be brought into line with it:

> periodical なジョブの正しい形を決めたじゃないですか？それに合わせて欲しい
> んです。

The decision above is therefore **Accepted** as written. Nothing in the
decision text changed; only its status.

**Why this section exists at all.** Between 2026-08-12 and 2026-08-16 the
ruling had been made in conversation and this header still read *awaiting
operator ruling*. An agent asked to "follow the standard" could grep the
repo and find a document that disclaims its own authority — so the answer
to "what is the correct form?" was unciteable even though it had been
decided. That is the same defect this ADR legislates against one level up:
a declaration whose authority lives somewhere the tooling cannot read is
not a declaration. A standard that cannot be cited cannot be enforced, and
an ADR left Proposed after its ruling is exactly that.

Consequently: **the ruling belongs in the file, not only in the thread.**
Any future ADR that is decided verbally should be flipped in the same
session, with the decider and date, before the conformance work starts.

## Consequences

- The "missing CRUD" gap closes without a second source of truth. `scaffold`
  answers create; `uninstall`/`disable` already answered delete; the overlay
  answers the per-host part of update.
- A job still cannot be conjured at runtime on one host. That is deliberate: it
  keeps `discover_jobs()` deterministic and keeps PS-226…PS-229 able to see every
  declaration in the fleet.
- `scaffold` requires a reinstall before the job appears. This is a real ergonomic
  cost and the honest one — it is the same cost every entry-point consumer pays,
  and hiding it is what a second registry would be buying.
- The overlay adds the first synced table outside cards. It must land with the five
  sync columns already present, so it should not ship before the replication
  primitive it depends on is exercised.
- If a future need genuinely requires declaring a job without shipping code, this
  ADR must be superseded rather than quietly worked around — and the superseding
  ADR owes an answer for how the AST auditor sees the new tier.

## Related

- ADR-0004 — execution fabric, unified `JobSpec`
- ADR-0006 — one store per host, consumed as a primitive
- ADR-0009 — opt-in auto-update in leaf packages (the distribution half of the same
  investigation)
- PR #566 — one CLI group per `JobSpec` kind
- PR #565 — PS-226…PS-229 job naming/declaration convention
