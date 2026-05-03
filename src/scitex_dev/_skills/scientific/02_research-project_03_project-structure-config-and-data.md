---
description: |
  [TOPIC] Research Project Config And Data
  [DETAILS] `./config/` and `./data/` for a SciTeX research project. `./config/` is the project-scope YAML tree (`PATH.yaml`, `PARAMS.yaml`, `EXPERIMENT.yaml`, `COLORS.yaml`) auto-loaded into `CONFIG` by `@stx.session`. `./data/` holds inputs and intermediate datasets — large files gitignored, symlinks tracked. Run outputs do NOT live in `./data/` — those go under `SDIR_OUT/` (auto-created by `@stx.session`). Pairs with [`02_research-project_07_config-and-parameters.md`](02_research-project_07_config-and-parameters.md) for CONFIG semantics.
tags: [scitex-scientific-research-project-project-structure-config-and-data]
---

# `./config` and `./data`

> Sibling leaves: [`./root`](02_research-project_01_project-structure-root.md) · [`./scripts`](02_research-project_02_project-structure-scripts.md) · [`./scripts/makefile`](02_research-project_04_project-structure-makefile.md) · [`./examples`](02_research-project_05_project-structure-examples.md) · [`./tests`](02_research-project_06_project-structure-tests.md)

## `./config` — project-scope YAML tree

Centralized project parameters, loaded into `CONFIG` by `@stx.session`. **Scripts pull parameters from here rather than hardcoding.**

```
./config/
├── PATH.yaml                            # paths to data, output, references
├── PARAMS.yaml                          # numeric / categorical parameters
├── EXPERIMENT.yaml                      # experiment-specific (per condition)
└── COLORS.yaml                          # plotting palette
```

- One YAML per logical concern (cheap to override one without touching others).
- `.gitkeep` so the directory exists even when empty.
- `@stx.session` deep-merges every file into a single `CONFIG` object exposed to `main(...)`.
- Resolution chain: **direct argument → CONFIG yaml → env var → default**. See [`02_research-project_07_config-and-parameters.md`](02_research-project_07_config-and-parameters.md) for full semantics, examples, override rules.

## `./data` — inputs + intermediate

```
./data/
├── raw/                                 # untouched inputs
├── processed/                           # outputs of an upstream pipeline; inputs for downstream
├── README.md                            # what's here, where it came from
└── <symlink>                            # → /path/on/NAS/cohort_X
```

- Project data files. **Large files gitignored.**
- Small files, `.gitkeep`, and symlinks may be tracked.
- Symlinks to artefacts let you navigate `./data/` as a centralized directory even when the bytes live elsewhere (NAS, scratch, HPC scratch).
- Provenance: each subdir or symlink should have a one-line note (in `./data/README.md` or sibling `<dir>.md`) saying where it came from.

## What does NOT go in `./data`

- **Run outputs** — those live under `SDIR_OUT/` (deterministic, per-script) or `SDIR_RUN/` (unique per invocation), auto-created by `@stx.session`. Committing run outputs to `./data/` pollutes inputs with derived artefacts.
- **External documents** — paper PDFs, third-party specs. SciTeX no longer uses a top-level `./references/` — fold provenance into `./data/<source>/README.md`.
- **Configuration** — that's `./config/`.

## Project-scope SciTeX state: `./.scitex/<pkg-short>/`

Adjacent to `./config/` and `./data/`, SciTeX packages may also keep **project-scope runtime state** under `./.scitex/<pkg-short>/`. Examples:

```
./.scitex/
├── dev/runtime/                         # scitex-dev session metadata
├── io/cache/                            # scitex-io project cache
└── cloud/                               # local data for scitex-cloud Django dev
```

- The `<pkg-short>` slug is the package name minus the `scitex-` prefix.
- Resolution chain (project-level → user-level): `<project>/.scitex/<pkg-short>/` falls back to `~/.scitex/<pkg-short>/`. See [`../general/01_ecosystem_06_local-state-directories.md`](../general/01_ecosystem_06_local-state-directories.md) for the full layout, `SCITEX_DIR` override, and `PathManager` usage.
- Default policy: gitignored (most contents are per-machine state). Some packages may track config files inside it — check the package's own `_skills/<pkg>/`.

## Audit hooks

The `audit-project` rules apply: `./config/` not directly checked (its presence is informational), `./data/` not directly checked. The lint rules that DO touch this area:

- `PS102` — `./references/` is forbidden at top level (fold provenance into `./data/<source>/README.md`).
- `PS401` — `./docs/to_claude/` must be gitignored (also applies to `./.scitex/<pkg>/runtime/` artefacts).
