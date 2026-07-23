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
   - [18_version-pinning-rules.md](18_version-pinning-rules.md) — full version-pinning rules (bounds, consumer minima bumps, coordinated waves, ecosystem layering)
   - [19_dev-extras-completeness.md](19_dev-extras-completeness.md) — `[dev]` extras completeness (fastmcp lesson, importorskip boundary, `PS-210`)
3. [03_modules-and-standalone-packages.md](03_modules-and-standalone-packages.md) — Module vs standalone package boundaries
4. [04_environment-variables.md](04_environment-variables.md) — `SCITEX_<MODULE_NAME>_*` prefix rule; mandates per-package `NN_env-vars.md` leaf
5. [05_re-export.md](05_re-export.md) — Umbrella `scitex.<name>` thin-re-export pattern + lazy-import guard
   - [20_re-export-patterns.md](20_re-export-patterns.md) — concrete bridge patterns (scholar named-re-export, release-gate check, `sys.modules` aliasing)
6. [06_dot_scitex_directory.md](06_dot_scitex_directory.md) — `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` layout, precedence, `SCITEX_DIR`, `PathManager`
   - [21_dot-scitex-roots-and-resolution.md](21_dot-scitex-roots-and-resolution.md) — §1–3.5 two roots, `runtime/`, prefix rule, precedence chain, lazy mkdir
   - [22_dot-scitex-what-goes-where.md](22_dot-scitex-what-goes-where.md) — §4 tracked-vs-runtime split, `{containers,bin}`, REPL cache
   - [23_dot-scitex-dotfiles-worked-example.md](23_dot-scitex-dotfiles-worked-example.md) — §4d dotfiles-tracked `~/.scitex/` CONFIG-vs-RUNTIME split
   - [24_dot-scitex-relocation-and-pathmanager.md](24_dot-scitex-relocation-and-pathmanager.md) — §5–8 forbidden paths, `$SCITEX_DIR`, `PathManager`, migration
   - [25_dot-scitex-cross-package-soc.md](25_dot-scitex-cross-package-soc.md) — §9 package owns a domain, plugin-port pattern (`PS-145`)
7. [07_license-and-cla.md](07_license-and-cla.md) — AGPL-3.0-only SPDX policy, CLA workflow template, `signatures/cla.json` shape, `pull_request_target` base-branch trap, bootstrap + audit recipes
8. [08_linter-plugins.md](08_linter-plugins.md) — Each package ships its own lint rules via the `scitex_dev.linter.plugins` entry point; `scitex-dev linter` aggregates; doc-block linting and ecosystem-wide `lint sweep`
9. [09_package-categories.md](09_package-categories.md) — Package category taxonomy
10. [10_research-project-type.md](10_research-project-type.md) — `project-type: research` — research repos are NOT pip packages; auditor SKIPS publish rules and KEEPS the universal ones
11. [11_model-serving-vs-consumption.md](11_model-serving-vs-consumption.md) — Model-serving (scitex-genai) vs model-consumption (sac via `ProviderSpec` `base_url`); contract is an HTTP endpoint, never a Python import — neither package imports the other
12. [12_local-state-resolution.md](12_local-state-resolution.md) — Resolve on-disk state via `scitex_config._ecosystem.local_state` by DATA NATURE: `path()` for config, `user_path()` for DATA/STATE stores (user-canonical, never project-shadowed), `runtime_path()` for ephemera; `$SCITEX_DIR` relocator; no-rolled-own-resolver mandate (PS-182)
13. [13_runtime-state-db-layout.md](13_runtime-state-db-layout.md) — Runtime-state DBs at `<proj-root>/.scitex/<pkg-short>/runtime/<pkg-short>.db` + optional `<subdir>/<unit>.db` shard pool; `runtime/` is THE off-GPFS redirect layer; a specialization of 12's `runtime_path()` (punim0264 GPFS inode-exhaustion incident, neurovista ADR-0022)
14. [14_credential-rotation-two-tier.md](14_credential-rotation-two-tier.md) — Two-tier master-host OAuth credential rotation: one MASTER refresher per account, CONSUMER hosts pull an access-only artifact; invariant CR-001 (exactly one refresh timer per account); `pooled` vs `exclusive:<label>` accounts; sac owns the mechanism, scitex-dev the convention
15. [15_credential-rotation-spartan-pull.md](15_credential-rotation-spartan-pull.md) — Spartan consumer deliverable of 14: `sac accounts pull-token` fetches the access-only envelope via SSH-fanout, split-writes the oauth artifact + `.credentials.meta.json`; pull-at-start + re-pull-under-1h + fail-loud starvation card
16. [16_boundary-ports-and-producers.md](16_boundary-ports-and-producers.md) — Cross-package import decision rule (port/producer vs direct import); the a1/a2/b/c/d edge-kind taxonomy from the 2026-07-08 audit; foundational-tier exemption; only unguarded top-level private cross-imports are the a2 smell (PS-183)
17. [17_config-layout-enforcement.md](17_config-layout-enforcement.md) — **PS-222**, the mechanical rule behind 06's tracked/`runtime/` split: everything under `.scitex/<pkg-short>/` is TRACKED except `runtime/`; primary config always `config.yaml`; a package scope is always a DIRECTORY; severity `W`, `audit.exemptions` opt-out
