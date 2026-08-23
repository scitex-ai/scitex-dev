---
description: |
  [TOPIC] `runtime/` — the redirectable local-state subtree; its `.db` DB-layout convention is WITHDRAWN
  [DETAILS] WITHDRAWN, not merely superseded-in-part — the constitution (§3 Craft) withdrew the `.db` runtime-state convention outright on 2026-08-23 after the operator ruled 「スクライトは使わない、憲法直しておいてください」, extending the 2026-08-16 ruling 「sqlite は根絶させてください」. A `.db` file IS SQLite. Runtime state has ONE home: per-host PostgreSQL on 55432. What survives is `runtime/` as the single redirectable subtree for regenerable NON-database local state (caches, scratch), and the rule that high-churn writes must not squat a shared inode quota — the punim0264 GPFS inode-exhaustion rationale (neurovista ADR-0022). A `.db` file under `runtime/` is a violation, not a shard. Read §1 first: it records the withdrawn text so nobody reconstructs it from a dangling citation; §0 records the earlier eradication ruling this one extends. The two exemplars this leaf once cited (scitex-session, scitex-clew) adopted the withdrawn convention and now describe legacy state. A specialization of 12's `runtime_path()` layer. Does NOT specify cross-store row identity (UUID) or per-table merge rules — both belong to the shared-state side and are unsettled.
tags: [scitex-general-ecosystem-runtime-state-db-layout]
---

# `runtime/` — the redirectable local-state subtree (the DB layout it once specified is WITHDRAWN)

**Read §1 first.** This leaf once pinned one degree of freedom — what a package's
SQLite DB is named and where inside `runtime/` it sits — and **that convention is
WITHDRAWN.** A `.db` file IS SQLite, and runtime state now has exactly one home:
the per-host PostgreSQL on 55432.

What survives, and all this leaf still governs: `06_dot_scitex_directory.md` puts
every package's regenerable state under `<pkg-short>/runtime/`,
`12_local-state-resolution.md` resolves that path via `runtime_path()`, and
`runtime/` remains the single redirectable subtree for regenerable **non-database**
local state — caches, scratch, working files — with the rule that high-churn writes
must not squat a shared inode quota.

§§1-3 are kept as a record of the withdrawn text, so that a reader who meets a
`.db` file on disk learns why it exists and that it is legacy. They are not
guidance. §0 records the earlier 2026-08-16 eradication ruling that this
withdrawal extends.

## 0. SQLITE IS BEING ERADICATED — read this before applying anything below

> **Operator ruling, 2026-08-16: 「sqlite は根絶させてください」** — eradicate
> SQLite. This supersedes the earlier reading of this leaf, including the
> version of this very section published hours earlier, which said `runtime/`
> keeps SQLite for regenerable local state. It does not.

| kind of state | where it lives |
|---|---|
| durable shared state (the board, cards, inboxes, agent registries) | per-host **PostgreSQL on 55432** |
| regenerable, local, high-churn (caches, shards, per-unit logs) | **PostgreSQL** — SQLite is not an exemption here either |
| design / specs | git |

**The rationale that justified SQLite here has itself evaporated, and that is
the point worth understanding rather than memorising.** §2a below records why
`runtime/` existed: the punim0264 GPFS inode-exhaustion incident, where
per-file DBs squatted a shared 7M-inode fileset until it was exhausted. That
argument was never *for SQLite* — it was against **millions of small files on
a shared filesystem**. PostgreSQL does not have that failure mode at all: one
server connection cannot exhaust an inode quota the way a shard pool did. So
eradicating SQLite does not cost this protection; it removes the need for it.

Everything in §§1-3 below describing `.db` naming, shard pools and suffix
choice is therefore **HISTORICAL**. Read it to understand deployed artifacts
you may still encounter — 12 `.db`/`.sqlite` files existed on this host when
the ruling landed — not as guidance for anything new.

**What this leaf still governs**, unchanged: `runtime/` as the single
redirectable subtree resolved through `runtime_path()`, and the rule that
high-churn state must not land on a shared inode quota. Those survive the
storage-engine change; the storage engine does not.

**Two things it still does NOT settle**, both belonging to the shared-state
side and unspecified as of 2026-08-16:

- **Row identity across stores.** Sequential per-store ids collide on merge.
  Measured by scitex-agent-container: consolidating 217 rows silently lost 94,
  because the same number meant different things in different stores. Shared
  state needs UUIDs, and the cost of changing that only rises with row count.
- **Merge rules per table.** Append-only threads (comments) union; mutable
  fields take the newest write; deletes need tombstones or they resurrect on
  the next merge. "Each host + synchronization" was written as though the
  second half existed; it did not.

**Provenance of this section, because it changed twice in one day.** Written
2026-08-16 to say this leaf governed only regenerable local state, on a
reading of the constitution's "This *extends* ... not replaces it". The
operator then ruled eradication outright, which supersedes that reading. Both
edits are recorded rather than overwritten silently: a spec that quietly
reverses itself teaches readers to distrust it, and the reversal here is
information — it says the boundary was contested and how it was settled.

**Two things this leaf does NOT specify, and must not be read as settling.**
Both belong to the Postgres/shared-state side and were, as of 2026-08-16,
specified nowhere:

- **Row identity across stores.** Sequential per-store ids collide on merge.
  Measured by scitex-agent-container: consolidating 217 rows silently lost 94,
  because the same number meant different things in different stores. Shared
  state needs UUIDs, and the cost of changing that only rises with row count.
- **Merge rules per table.** Append-only threads (comments) union; mutable
  fields take the newest write; deletes need tombstones or they resurrect on
  the next merge. "Each host + synchronization" was written as though the
  second half existed; it did not.

Neither is settled here because neither is a *layout* question. They are
recorded so the next reader does not mistake this leaf's silence for a ruling
that none is needed.

## 1. THE CONVENTION IS WITHDRAWN — there is no `.db` layout to follow

> **WITHDRAWN 2026-08-23 by the constitution (§3 Craft).** Operator ruling,
> Telegram, unprompted (katakana spelling 「スクライト」 is his):
>
> > 「スクライトは使わない、憲法直しておいてください」
> > *(translation: we do not use SQLite; fix the constitution.)*
>
> **A `.db` file IS SQLite.** This section specified one, three lines from a
> "never SQLite" rule it contradicted — and the contradiction was
> load-bearing in exactly one direction: this section was the SPECIFIC,
> path-level, copy-pasteable one, so a reader implementing a new package
> followed it rather than the general prohibition. That is the failure mode,
> not a footnote about it.

**Runtime state has exactly one home: the per-host PostgreSQL on 55432.**
`runtime/` survives ONLY for regenerable, NON-database local state — caches,
scratch, redirectable working files. A `.db` file inside it is a violation,
not a shard.

*The withdrawn text, kept so nobody reconstructs it from a dangling
citation:* a package's runtime-state DB lived at
`<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db`, with an optional
`<subdir>/<unit>.db` sub-pool for sharded / per-unit DBs, resolved through
`local_state.runtime_path(pkg)`.

**What still holds from that text:** resolve `runtime/` through
`local_state.runtime_path(pkg)` (12 §1), never a `Path.home() / ".scitex/..."`
literal. The resolver was never the problem; what it resolved to was.

## 2. Rationale

**2a. `runtime/` is THE off-GPFS redirect layer.** `runtime/` is regenerable, gitignored, PathManager-resolvable local state (06 §4b). Because it is *one* subtree resolved through `runtime_path()`, it is also the single layer you redirect off a shared / GPFS filesystem — point `$SCITEX_DIR` (or a package base-redirect env var) at node-local scratch and every DB moves atomically. High-cardinality DB writes MUST NOT land on a shared inode quota. This convention emerged from the **punim0264 GPFS inode-exhaustion incident**: in-repo `.scitex/*/…` DBs squatted a shared 7M-inode fileset and exhausted it.

**2b. WITHDRAWN — `.db` was the interop-safe suffix, and there is now no runtime DB to name.** Kept only because a reader who finds `.db` files on disk deserves to know why they exist and that they are legacy. Do NOT use this to justify a new one; new runtime state goes to PostgreSQL on 55432.

*Historical rationale, in the past tense on purpose — the sentences below were once
instructions and are now a record of why the deployed files look the way they do:*
scitex-io's load dispatch registered **only** `.db` (`register_loader(".db", …)` at
`scitex_io/_optional_providers.py:173`); scitex-db is itself extension-agnostic, so
`.db` was the one suffix that round-tripped through `stx.io.load()`, and it matched
the existing `pac_db/{hash}.db` precedent. That is why every legacy runtime DB is
named `*.db`. A parallel operator request was wiring `.sqlite` → the same loader,
and the convention stayed `.db`; neither suffix is to be used for anything new.

**2c. HISTORICAL (the shard pool it describes is withdrawn). HPC: symlink the shard subdir to node-local scratch.** The node-local-scratch technique survives for regenerable NON-database working files; the merged-DB half does not. On a cluster the shard/unit subdir (`runtime/<subdir>/`) MAY be a symlink → node-local scratch (`$TMPDIR`, `/local/…`); only the merged `<pkg-short>.db` lands on the persistent filesystem. High-churn per-unit writes stay node-local; the durable artifact is the single merged DB.

## 3. Exemplars

| Package | Primary | Sub-pool | Notes |
|---|---|---|---|
| **scitex-session** | `.scitex/session/runtime/session.db` | `sessions/session-NNNN.db` | Fixed-N shard pool. PR #34 shipped the `SCITEX_SESSION_OUT_DIR` base redirect (the off-GPFS lever per §2a). |
| **scitex-clew** | `.scitex/clew/runtime/clew.db` | `hosts/<host>.db` | Per-host multi-DB; a transparent auto-rename shim migrates legacy names in place. |

Both keep the primary DB at `runtime/<pkg-short>.db` and shard under a package-named subdir.

> **DO NOT COPY THIS PATTERN.** This line previously read "the pattern any
> new DB-backed package copies", and that instruction is exactly how the
> withdrawn convention would keep propagating after the constitution
> withdrew it. These two are ADOPTERS OF A WITHDRAWN CONVENTION, recorded
> so their on-disk files are explicable — not exemplars to follow. A new
> package puts its state in the per-host PostgreSQL on 55432.

## 4. Related

- `01_ecosystem/12_local-state-resolution.md` — the config-vs-data-vs-runtime RESOLUTION rule. This leaf is a **specialization of its `runtime_path()` layer**: 12 says *where* runtime state resolves; this says *how* the DBs inside it are named and laid out.
- `01_ecosystem/06_dot_scitex_directory.md` §4b — `runtime/` holds `*.db`; the gitignore + `.gitkeep`/`README.md` seed contract.
- PS-145 / PS-146 / PS-147 / PS-182 local-state audits — `scitex_dev/_cli/audit/_project/_check_local_state.py` (cross-package read / pip-install side-effect / eval-form completion) + `_check_path_resolver.py` (rolled-own resolver). They enforce the resolution side this layout sits on.
- **neurovista ADR-0022** (`docs/adr/0022-session-logs-db-backed-sharded.md`, "Session logs are DB-backed (sharded); artifacts stay loose and symlinked") — the incident / design source (a Proposed draft). neurovista adds the constitution pointer here post-merge.
