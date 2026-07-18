---
description: |
  [TOPIC] Ecosystem Runtime-State-DB Layout — where package DBs live on disk
  [DETAILS] Every scitex-* package's runtime-state DB lives at `<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db`, with an optional `<subdir>/<unit>.db` sub-pool for sharded / per-unit DBs. Rationale: `runtime/` is THE layer you redirect off shared/GPFS filesystems (high-cardinality writes must not squat a shared inode quota); `.db` is scitex-io's only recognized DB suffix; on HPC the shard subdir can symlink to node-local scratch. Two adopting exemplars (scitex-session, scitex-clew). A specialization of 12's `runtime_path()` layer; born from the punim0264 GPFS inode-exhaustion incident (neurovista ADR-0022).
tags: [scitex-general-ecosystem-runtime-state-db-layout]
---

# Runtime-State-DB Layout — where package DBs live on disk

`06_dot_scitex_directory.md` puts every package's regenerable state under `<pkg-short>/runtime/`; `12_local-state-resolution.md` resolves that path via `runtime_path()`. This leaf pins the one remaining degree of freedom: **what a package's SQLite DB is named and where inside `runtime/` it sits** — so every DB-backed package lays out the same way and the whole `runtime/` subtree stays a single redirectable unit.

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
