---
description: |
  [TOPIC] Ecosystem Runtime-State-DB Layout — where package DBs live on disk
  [DETAILS] Governs REGENERABLE LOCAL state only — durable shared state lives in per-host PostgreSQL on 55432 (constitution §3); see §0 before applying this. Every scitex-* package's runtime-state DB lives at `<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db`, with an optional `<subdir>/<unit>.db` sub-pool for sharded / per-unit DBs. Rationale: `runtime/` is THE layer you redirect off shared/GPFS filesystems (high-cardinality writes must not squat a shared inode quota); `.db` is scitex-io's only recognized DB suffix; on HPC the shard subdir can symlink to node-local scratch. Two adopting exemplars (scitex-session, scitex-clew). A specialization of 12's `runtime_path()` layer; born from the punim0264 GPFS inode-exhaustion incident (neurovista ADR-0022). Does NOT specify cross-store row identity (UUID) or per-table merge rules — both belong to the shared-state side and are unsettled.
tags: [scitex-general-ecosystem-runtime-state-db-layout]
---

# Runtime-State-DB Layout — where package DBs live on disk

`06_dot_scitex_directory.md` puts every package's regenerable state under `<pkg-short>/runtime/`; `12_local-state-resolution.md` resolves that path via `runtime_path()`. This leaf pins the one remaining degree of freedom: **what a package's SQLite DB is named and where inside `runtime/` it sits** — so every DB-backed package lays out the same way and the whole `runtime/` subtree stays a single redirectable unit.

Read §0 first: this governs regenerable LOCAL state. Durable shared state goes to per-host PostgreSQL on 55432, never SQLite.

## 0. WHICH STATE THIS GOVERNS — read this before applying anything below

This leaf governs **REGENERABLE LOCAL state only**. It does not govern durable
shared state, and applying it there is the failure it now warns about.

| kind of state | where it lives | governed by |
|---|---|---|
| regenerable, local, high-churn (caches, shards, per-unit logs) | `runtime/<pkg-short>.db`, SQLite | **this leaf** |
| durable shared state (the board, cards, inboxes, agent registries) | per-host **PostgreSQL on 55432**, synchronized across hosts | the constitution, §3 |
| design / specs | git | the constitution, §3 |

The operator's ruling, 2026-08-14: 「spec は設計書、状態は db (55432 postgres;
each host, synchronization across hosts)」 — and the constitution is explicit
that the Postgres rule **extends this leaf rather than replacing it**:
`runtime/` stays for regenerable local state only. So both are live, and the
question a reader must answer first is *which kind of state am I holding*.

**Why this section was added (2026-08-16).** It was not here, and the omission
was load-bearing. The operator asked whether the fleet should move to one
Postgres or keep per-host stores, and the honest answer turned out to be
neither-globally: per-host is right for high-churn runtime state — the
punim0264 GPFS inode-exhaustion incident in §2a is still true and is still the
reason — while one store is right for the shared board, where volume is low
and silent divergence is the actual harm. Collapsing everything to one side
discards one of those two reasons. A spec that describes only one class, and
does not say it is only one class, invites exactly that collapse.

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

## 1. The convention

> A package's runtime-state DB lives at
> **`<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db`**,
> with an optional **`<subdir>/<unit>.db`** sub-pool for sharded / per-unit DBs.

| Role | Path (relative to the `<pkg-short>/` root) | Example (`scitex-session`) |
|---|---|---|
| Primary / merged DB | `runtime/<pkg-short>.db` | `runtime/session.db` |
| Shard / per-unit pool | `runtime/<subdir>/<unit>.db` | `runtime/sessions/session-0007.db` |

Resolve the base through `local_state.runtime_path(pkg)` (12 §1) — never a `Path.home() / ".scitex/..."` literal. The subdir name is the package's choice (`sessions/`, `hosts/`, …); the `.db` suffix and the `runtime/` parent are fixed.

## 2. Rationale

**2a. `runtime/` is THE off-GPFS redirect layer.** `runtime/` is regenerable, gitignored, PathManager-resolvable local state (06 §4b). Because it is *one* subtree resolved through `runtime_path()`, it is also the single layer you redirect off a shared / GPFS filesystem — point `$SCITEX_DIR` (or a package base-redirect env var) at node-local scratch and every DB moves atomically. High-cardinality DB writes MUST NOT land on a shared inode quota. This convention emerged from the **punim0264 GPFS inode-exhaustion incident**: in-repo `.scitex/*/…` DBs squatted a shared 7M-inode fileset and exhausted it.

**2b. `.db` is the interop-safe suffix.** scitex-io's load dispatch registers **only** `.db` (`register_loader(".db", …)` at `scitex_io/_optional_providers.py:173`); scitex-db is itself extension-agnostic, so `.db` is the one suffix that round-trips through `stx.io.load()`, and it matches the existing `pac_db/{hash}.db` precedent. Name every runtime DB `*.db`. (A parallel operator request is wiring `.sqlite` → the same loader in scitex-io, but the **naming convention stays `.db`** — do not adopt `.sqlite` for new DBs.)

**2c. HPC: symlink the shard subdir to node-local scratch.** On a cluster the shard/unit subdir (`runtime/<subdir>/`) MAY be a symlink → node-local scratch (`$TMPDIR`, `/local/…`); only the merged `<pkg-short>.db` lands on the persistent filesystem. High-churn per-unit writes stay node-local; the durable artifact is the single merged DB.

## 3. Exemplars

| Package | Primary | Sub-pool | Notes |
|---|---|---|---|
| **scitex-session** | `.scitex/session/runtime/session.db` | `sessions/session-NNNN.db` | Fixed-N shard pool. PR #34 shipped the `SCITEX_SESSION_OUT_DIR` base redirect (the off-GPFS lever per §2a). |
| **scitex-clew** | `.scitex/clew/runtime/clew.db` | `hosts/<host>.db` | Per-host multi-DB; a transparent auto-rename shim migrates legacy names in place. |

Both keep the primary DB at `runtime/<pkg-short>.db` and shard under a package-named subdir — the pattern any new DB-backed package copies.

## 4. Related

- `01_ecosystem/12_local-state-resolution.md` — the config-vs-data-vs-runtime RESOLUTION rule. This leaf is a **specialization of its `runtime_path()` layer**: 12 says *where* runtime state resolves; this says *how* the DBs inside it are named and laid out.
- `01_ecosystem/06_dot_scitex_directory.md` §4b — `runtime/` holds `*.db`; the gitignore + `.gitkeep`/`README.md` seed contract.
- PS-145 / PS-146 / PS-147 / PS-182 local-state audits — `scitex_dev/_cli/audit/_project/_check_local_state.py` (cross-package read / pip-install side-effect / eval-form completion) + `_check_path_resolver.py` (rolled-own resolver). They enforce the resolution side this layout sits on.
- **neurovista ADR-0022** (`docs/adr/0022-session-logs-db-backed-sharded.md`, "Session logs are DB-backed (sharded); artifacts stay loose and symlinked") — the incident / design source (a Proposed draft). neurovista adds the constitution pointer here post-merge.
