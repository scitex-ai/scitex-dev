---
description: |
  [TOPIC] Ecosystem Wide Rules
  [DETAILS] Cross-package conventions every `scitex-*` repo follows — the 3-layer cascade hierarchy and test scope, dependency hygiene + optional extras + version-pinning rules, the module-vs-standalone-package decision, the `SCITEX_<MODULE_NAME>_*` env-var prefix rule, the umbrella `scitex.<name>` thin-re-export bridge with lazy-import guard, the `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` local-state layout, AGPL-3.0-only + CLA policy, per-package linter plugins, package categories, the `project-type: research` auditor carve-outs, and the model-serving (scitex-genai) vs model-consumption (sac) HTTP-only boundary. Use when touching any `scitex-*` package or onboarding a research repo to ecosystem standards.
tags: [scitex-general-ecosystem-index]
---

# Ecosystem-wide Rules (SciTeX) — Index

Cross-package conventions every `scitex-*` repo follows. Audience: anyone
touching any `scitex-*` package. Read before the per-package tiers
([../SKILL.md](../SKILL.md)).

## Sections

1. [01_upstream-and-downstream.md](01_upstream-and-downstream.md) — 3-layer cascade, test scope, cascade pattern
2. [02_dependency-and-version-pinning.md](02_dependency-and-version-pinning.md) — Dependency hygiene, optional extras, version-pinning rules
3. [03_modules-and-standalone-packages.md](03_modules-and-standalone-packages.md) — Module vs standalone package boundaries
4. [04_environment-variables.md](04_environment-variables.md) — `SCITEX_<MODULE_NAME>_*` prefix rule; mandates per-package `NN_env-vars.md` leaf
5. [05_re-export.md](05_re-export.md) — Umbrella `scitex.<name>` thin-re-export pattern + lazy-import guard
6. [06_dot_scitex_directory.md](06_dot_scitex_directory.md) — `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` layout, precedence, `SCITEX_DIR`, `PathManager`
7. [07_license-and-cla.md](07_license-and-cla.md) — AGPL-3.0-only SPDX policy, CLA workflow template, `signatures/cla.json` shape, `pull_request_target` base-branch trap, bootstrap + audit recipes
8. [08_linter-plugins.md](08_linter-plugins.md) — Each package ships its own lint rules via the `scitex_dev.linter.plugins` entry point; `scitex-dev linter` aggregates; doc-block linting and ecosystem-wide `lint sweep`
9. [09_package-categories.md](09_package-categories.md) — Package category taxonomy
10. [10_research-project-type.md](10_research-project-type.md) — `project-type: research` — research repos are NOT pip packages; auditor SKIPS publish rules and KEEPS the universal ones
11. [11_model-serving-vs-consumption.md](11_model-serving-vs-consumption.md) — Model-serving (scitex-genai) vs model-consumption (sac via `ProviderSpec` `base_url`); contract is an HTTP endpoint, never a Python import — neither package imports the other
12. [12_local-state-resolution.md](12_local-state-resolution.md) — Resolve on-disk state via `scitex_config._ecosystem.local_state` by DATA NATURE: `path()` for config, `user_path()` for DATA/STATE stores (user-canonical, never project-shadowed — the anti-footgun rule), `runtime_path()` for ephemera; `$SCITEX_DIR` relocator; no-rolled-own-resolver mandate (PS-182)
13. [13_runtime-state-db-layout.md](13_runtime-state-db-layout.md) — Runtime-state DBs live at `<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db` + optional `<subdir>/<unit>.db` shard pool; `.db` is scitex-io's only recognized suffix; `runtime/` is THE off-GPFS redirect layer (shard subdir may symlink to node-local scratch); a specialization of 12's `runtime_path()` layer (born from the punim0264 GPFS inode-exhaustion incident, neurovista ADR-0022)
14. [14_credential-rotation-two-tier.md](14_credential-rotation-two-tier.md) — Two-tier master-host OAuth credential rotation: a MASTER host is the SOLE refresher per account (rotating refresh_tokens ⇒ >1 refresher mutually invalidates ⇒ quota stall); CONSUMER hosts PULL a short-lived ACCESS-ONLY artifact (`refreshToken` structurally absent ⇒ they literally cannot refresh). Auditable invariant CR-001: exactly one refresh timer per account, fleet-wide. Account `pooled` (healthy+lowest-quota selector) vs `exclusive:<label>` (strict, no substitute); listen-bearer over the mesh (consumer #3) + SSH-fanout fallback; mint-on-pull cadence; fail-loud starvation card on degrade. sac owns the mechanism, scitex-dev owns the convention
15. [15_credential-rotation-spartan-pull.md](15_credential-rotation-spartan-pull.md) — The Spartan consumer deliverable of 14: `sac accounts pull-token --account <label|auto> --out ~/.claude/.credentials.json` fetches the access-only envelope via SSH-fanout (no-listen host), split-writes the oauth artifact + `.credentials.meta.json` atomically, prints `{account, expires_at}` for the caller's re-pull scheduler; clew wires the receive side; pull-at-start + re-pull-under-1h-to-expiry + fail-loud starvation card
16. [16_boundary-ports-and-producers.md](16_boundary-ports-and-producers.md) — Cross-package import decision rule ("must the consumer work without the producer, or should third parties plug in? → port/producer; else → direct import"); the a1/a2/b/c/d edge-kind taxonomy from the 2026-07-08 ecosystem audit; foundational-tier exemption (io/config/logging/str/dict/context/path/types); methodology caveat — a static import scan can't tell hard-vs-guarded/lazy/TYPE_CHECKING, so only unguarded top-level private cross-imports are the a2 smell (PS-183)
