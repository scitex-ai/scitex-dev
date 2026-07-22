---
name: general
description: |
  [WHAT] Canonical engineering standards every `scitex-*` package and research project must follow — 3-layer architecture cascade, dependency/version pinning, local-state directory layout (`~/.scitex/<pkg-short>/` and `<project>/.scitex/<pkg-short>/`), repo layout (src/tests/scripts/examples), the five interfaces (Python API → CLI → MCP → Skills → optional HTTP) with their delegation rules and the noun-verb CLI convention, README/Sphinx docs, version-control workflow plus `scitex-dev ecosystem …` release automation, skill-authoring rules (layout, editable-vs-wheel install, public-vs-private), and the periodic quality checklist. Use as the single entry point for creating, auditing, reviewing, or releasing any SciTeX package.
  [WHEN] Creating, auditing, reviewing, or releasing any SciTeX package, or onboarding a research repo to ecosystem standards.
  [HOW] Read SKILL.md as the index, then drill into the per-category sub-dirs (`01_ecosystem/`, `02_package/`, `03_interface/`, `04_docs/`, `05_development/`, `09_quality/`), each with its own `SKILL.md` index, for the relevant tier.
tags: [scitex-general]
user-invocable: false
primary_interface: mixed
interfaces:
  python: 0-3
  cli: 0-3
  mcp: 0-3
  skills: 3
  http: 0
---

# SciTeX General Standards

`pip install scitex` — standards for all ecosystem packages.

(Interface star ratings live on each interface section header, not in a single
summary callout. See `03_interface/04_skills/13_standard-template.md`.)

## Sub-skills

This is a **parent index**: it links the six category indexes, and each of
those enumerates its own leaves. Read in this order when building or auditing
a package — each tier presupposes the ones above it.

**Three tiers of concerns:**

- **§1 — Ecosystem-wide rules** (cross-package conventions every `scitex-*`
  repo follows). Audience: anyone touching any `scitex-*` package.
- **§2–§5 — Per-package concerns** (how to build, document, and ship a single
  `scitex-*` repo). Audience: package authors.
- **§9 — Ecosystem quality** (cross-package periodic audits). Audience:
  ecosystem maintainers.

> Research-project usage (`@stx.session`, `CONFIG`, `SDIR_OUT`/`SDIR_RUN`)
> lives in [`../scientific/`](../scientific/SKILL.md) — that is
> research-methodology, not package engineering.

### 1. [01_ecosystem/](01_ecosystem/SKILL.md) — what every `scitex-*` package must follow

3-layer cascade and test scope, dependency hygiene and version pinning,
module-vs-standalone boundaries, the `SCITEX_<MODULE_NAME>_*` env-var prefix,
the umbrella thin-re-export bridge, `.scitex/<pkg-short>/` local-state layout
and resolution, AGPL-3.0-only + CLA policy, per-package linter plugins,
`project-type: research` carve-outs, boundary ports vs direct imports,
credential-rotation conventions.

### 2. [02_package/](02_package/SKILL.md) — how does *this* repo live on disk?

Repo-root rules and per-directory structure (`src/`, `scripts/`, `examples/`,
`tests/`, makefile dispatcher), GitHub Actions, repository-level quality,
browser-automation debug artifacts, per-package `.venv` isolation, CI +
codecov wiring, the no-mocks mandate (STX-NM), and the test-quality family
(STX-TQ).

### 3. [03_interface/](03_interface/SKILL.md) — how do users and agents touch this package?

The five interfaces and their delegation chain: Python API, CLI (noun-verb),
MCP, Skills authoring, and the optional HTTP API. Each has its own nested
index.

### 4. [04_docs/](04_docs/SKILL.md) — how does this package become understandable?

README template and badges, Sphinx configuration, Read the Docs onboarding,
robust docs-CI under `sphinx-build -W`, env-vars/state documentation, and ADRs.

### 5. [05_development/](05_development/SKILL.md) — version control, periodic audits, release

Branches, tags and release gates; running `audit-all` continuously; release
automation and the ecosystem sync CLI; subprocess-coverage wiring; demo smoke
tests; the 30%→90% coverage-push playbook; the per-peer TQ/no-mocks migration
playbook.

### 9. [09_quality/](09_quality/SKILL.md) — periodic cross-package audits, run when something feels off

Crash-early/crash-loud fail-fast discipline; the severity-tagged failure
triage table and its two recipe leaves (packaging/release failures vs
compat/refactor drift); the `/speak-and-call` quality checklist and its
release-gate probes; the verification doctrine by claim type and its
companion on controls that license nothing.

### Scratch
- [40_playground.md](40_playground.md) — Scratch notes
