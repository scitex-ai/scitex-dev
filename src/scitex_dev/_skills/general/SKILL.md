---
name: general
description: |
  [WHAT] Canonical engineering standards every `scitex-*` package and research project must follow — 3-layer architecture cascade, dependency/version pinning, local-state directory layout (`~/.scitex/<pkg-short>/` and `<project>/.scitex/<pkg-short>/`), repo layout (src/tests/scripts/examples), the five interfaces (Python API → CLI → MCP → Skills → optional HTTP) with their delegation rules and the noun-verb CLI convention, README/Sphinx docs, version-control workflow plus `scitex-dev ecosystem …` release automation, skill-authoring rules (layout, editable-vs-wheel install, public-vs-private), and the periodic quality checklist. Use as the single entry point for creating, auditing, reviewing, or releasing any SciTeX package.
  [WHEN] Creating, auditing, reviewing, or releasing any SciTeX package, or onboarding a research repo to ecosystem standards.
  [HOW] Read SKILL.md as the index, then drill into the numbered sub-skill leaves (`01_ecosystem_*`, `02_package_*`, `03_interface_*`, `04_docs_*`, `05_development_*`, `98_quality_*`) for the relevant tier.
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

(Interface star ratings live on each interface section header below, not
in a single summary callout. See
`03_interface_04_skills/13_standard-template.md`.)

## Sub-skills

Read in this order when building or auditing a package. Each section presupposes the ones above it.

**Three tiers of concerns:**

- **§1 — Ecosystem-wide rules** (cross-package conventions every `scitex-*` repo follows): cascade hierarchy, dependency pinning, module-vs-standalone decisions, env-var prefix, re-export bridge, local-state directory layout. Audience: anyone touching any `scitex-*` package.
- **§2–§5 — Per-package concerns** (how to build, document, and ship a single `scitex-*` repo): package layout, the five interfaces (Skills authoring is now §3.4 under Interfaces), docs, release flow. Audience: package authors.
- **§8 — Ecosystem quality** (cross-package periodic audits): failure playbook, quality checklist. Audience: ecosystem maintainers.

> Research-project usage (`@stx.session`, `CONFIG`, `SDIR_OUT`/`SDIR_RUN`) lives in [`../scientific/`](../scientific/SKILL.md) — that is research-methodology, not package engineering.

### 1. Ecosystem-wide rules — what every `scitex-*` package must follow
- [01_ecosystem_01_upstream-and-downstream.md](01_ecosystem_01_upstream-and-downstream.md) — 3-layer cascade, test scope, cascade pattern
- [01_ecosystem_02_dependency-and-version-pinning.md](01_ecosystem_02_dependency-and-version-pinning.md) — Dependency hygiene, optional extras, version-pinning rules
- [01_ecosystem_03_modules-and-standalone-packages.md](01_ecosystem_03_modules-and-standalone-packages.md) — Module vs standalone package boundaries
- [01_ecosystem_04_environment-variables.md](01_ecosystem_04_environment-variables.md) — `SCITEX_<MODULE_NAME>_*` prefix rule; mandates per-package `NN_env-vars.md` leaf
- [01_ecosystem_05_re-export.md](01_ecosystem_05_re-export.md) — Umbrella `scitex.<name>` thin-re-export pattern + lazy-import guard
- [01_ecosystem_06_local-state-directories.md](01_ecosystem_06_local-state-directories.md) — `<project>/.scitex/<pkg-short>/` + `~/.scitex/<pkg-short>/` layout, precedence, `SCITEX_DIR`, `PathManager`
- [01_ecosystem_07_license-and-cla.md](01_ecosystem_07_license-and-cla.md) — AGPL-3.0-only SPDX policy, CLA workflow template, `signatures/cla.json` shape (object, not bare array), `pull_request_target` base-branch trap, bootstrap + audit recipes
- [01_ecosystem_08_linter-plugins.md](01_ecosystem_08_linter-plugins.md) — Each package ships its own lint rules via the `scitex_dev.linter.plugins` entry point; `scitex-dev linter` aggregates. Engine in `scitex_dev.linter` (formerly `scitex-linter`); rules live next to the API they enforce. Doc-block linting (`.md`/`.rst`/`.ipynb`) and ecosystem-wide `lint sweep`.

### 2. Package — how does *this* `scitex-*` package's repo live on disk?
Project structure split into one leaf per top-level directory:
- [02_package_01_project-structure-root.md](02_package_01_project-structure-root.md) — Repo-root rules, allowed files, forbidden top-level dirs, `./docs/`, `./templates/` wheel-vs-git, anti-patterns, pre-release checklist
- [02_package_02_project-structure-src.md](02_package_02_project-structure-src.md) — `src/<pkg>/` layout, absolute imports, cascade direction (umbrella `scitex` is the only forbidden import from `src/`), public/private filename convention
- [02_package_03_project-structure-scripts.md](02_package_03_project-structure-scripts.md) — `./scripts/` for maintenance + scientific analysis (not shipped); graduation to `examples/` or `src/`
- [02_package_04_project-structure-makefile.md](02_package_04_project-structure-makefile.md) — `./scripts/makefile/` per-target dispatcher pattern + canonical target inventory
- [02_package_05_project-structure-examples.md](02_package_05_project-structure-examples.md) — Numbered examples + `_out/` artefacts committed + `00_run_all.sh` + matched `tests/examples/test_*.py`
- [02_package_06_project-structure-tests.md](02_package_06_project-structure-tests.md) — `tests/<pkg>/` mandatory parent, allowed subdirs, public/private mirroring, allowed root meta-tests, `audit-project` rules
- [02_package_07_github-actions.md](02_package_07_github-actions.md) — CI, PyPI publish, CLA, reusable workflow patterns
- [02_package_08_quality.md](02_package_08_quality.md) — Repository-level quality (AGPL, Four Freedoms, README rules, GitHub setup)
- [02_package_09_browser-automation-debugging.md](02_package_09_browser-automation-debugging.md) — Playwright debug-artifact capture for every browser-automation file (PA-305 rule)
- [02_package_10_dev-venv-isolation.md](02_package_10_dev-venv-isolation.md) — Real isolated `<pkg-root>/.venv/` per peer (no symlinks to `~/.venv`); CI-parity local dev setup; `scitex-dev ecosystem install --venv per-package` (default)

### 3. Interfaces — how do users and agents touch *this* package?
- [03_interface_00_overview.md](03_interface_00_overview.md) — Five interfaces: overview and delegation chain
- [03_interface_01_python-api/](03_interface_01_python-api/) — Minimal API, `__all__`, lazy imports, NumPy docstrings, version strategy (split into per-section files; start at [SKILL.md](03_interface_01_python-api/SKILL.md))
- [03_interface_02_cli/](03_interface_02_cli/) — Required sub-commands, flags, noun-verb convention, AI-friendly rules (split into per-section files; start at [SKILL.md](03_interface_02_cli/SKILL.md))
- [03_interface_03_mcp/SKILL.md](03_interface_03_mcp/SKILL.md) — fastmcp, tool naming, reproducibility, standard commands
- [03_interface_04_skills/](03_interface_04_skills/) — `_skills/` layout, SKILL.md format, registration, export, frontmatter, public-vs-private (split into per-section files; start at [SKILL.md](03_interface_04_skills/SKILL.md))
- [03_interface_05_http-api/](03_interface_05_http-api/) (split into per-section files; start at [SKILL.md](03_interface_05_http-api/SKILL.md)) — Optional FastAPI delegation

### 4. Documentation — how does *this* package become understandable?
- [04_docs_01_readme.md](04_docs_01_readme.md) — Standard README template, sections, badges, footer
- [04_docs_02_sphinx.md](04_docs_02_sphinx.md) — Sphinx docs, conf.py, troubleshooting
- [04_docs_03_rtd.md](04_docs_03_rtd.md) — Read the Docs onboarding, `.readthedocs.yaml`, build config

### 5. Development — version control, periodic audits, release
- [05_development_01_version-control.md](05_development_01_version-control.md) — Branches, tags, release waves, release gates (core workflow)
- [05_development_02_periodic-audits.md](05_development_02_periodic-audits.md) — Run `audit-all` continuously while editing — cron / tmux / agent loops, JSON contract for programmatic consumers, Claude Code `CronCreate` / `ScheduleWakeup` / `Monitor` mechanisms
- [05_development_03_release-automation.md](05_development_03_release-automation.md) — Automation commands, ecosystem sync CLI, MCP tools, Python API

### 8. Ecosystem quality — periodic cross-package audits, run when something feels off
- [98_quality_01_failure-playbook.md](98_quality_01_failure-playbook.md) — Severity-tagged cookbook of ecosystem failure modes
- [99_quality_02_checklist.md](99_quality_02_checklist.md) — Strategic /speak-and-call runbook with append-only log

### Scratch
- [40_playground.md](40_playground.md) — Scratch notes
