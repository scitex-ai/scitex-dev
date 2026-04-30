---
name: research-project-structure
description: Canonical top-level layout for a SciTeX *research project* (analysis pipelines, experiments) — distinct from a pip-package layout. Covers `./scripts/` as the primary code location (analysis pipelines invoked with `@stx.session`, mirrored by `./tests/scripts/` 1:1), `./config/` as the project-scope CONFIG yaml tree (PATH/PARAMS/EXPERIMENT, loaded automatically by `@stx.session`), `./data/` (large files gitignored; symlinks tracked), `./examples/` (numbered + `_out/` committed), `./references/` (read-only external material), the `SDIR_OUT`/`SDIR_RUN` injected paths for deterministic round-trips, what's allowed at the repo root, and anti-patterns. Pairs with [`02_research-project_02_config-and-parameters.md`](02_research-project_02_config-and-parameters.md) for the CONFIG semantics. For *package* layout, see [`../general/02_package_01_project-structure.md`](../general/02_package_01_project-structure.md).
tags: [scitex-python, scitex-scientific, research, project-structure, layout]
---

# Research-Project Structure

Layout for a SciTeX-based **research project** — analysis pipelines and
experiments rather than a shippable package. The same "every directory has
one purpose" rule applies; the directories themselves differ.

> Building a *pip-installable package* instead? See [`../general/02_package_01_project-structure.md`](../general/02_package_01_project-structure.md).

## Top-level directories

### `./scripts` — the primary code location

A research project's `./scripts/` is what `./src/` is to a package. Pipelines, analyses, model-training runs all live here.

- Each script entered via `@stx.session` so `CONFIG`, `SDIR_OUT`, `SDIR_RUN`, `logger`, and `plt` are auto-injected (see [02_research-project_02_config-and-parameters.md](02_research-project_02_config-and-parameters.md)).
- Helpers used by multiple scripts go in `./scripts/utils/`.
- Free to depend on SciTeX, third-party tools, etc.
- Pipelines that produce a result worth keeping should land artifacts under their `SDIR_OUT/` (auto-created by `@stx.session`).

```python
# scripts/analysis/01_load_and_summarize.py
import scitex as stx

@stx.session
def main(
    data_path: str = "./data/raw.parquet",
    n_samples: int = 100,
    CONFIG=stx.session.INJECTED,
    SDIR_OUT=stx.session.INJECTED,
    plt=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    df = stx.io.load(data_path).head(n_samples)
    fig = plt.figure(); df.plot(ax=fig.gca())
    stx.io.save(fig, SDIR_OUT / "summary.png")
    return 0
```

#### `./scripts/makefile/` — Makefile target backing scripts

The root `Makefile` is a thin dispatcher; each target's actual logic lives as one script under `./scripts/makefile/` (`install.sh`, `test-changed.sh`, `coverage-html.sh`, `lint.sh`, `clean.sh`, …). Each is independently runnable from the shell. Same pattern as for packages — see [`../general/02_package_01_project-structure.md`](../general/02_package_01_project-structure.md#scriptsmakefile--makefile-target-backing-scripts) for the full layout.

### `./tests` — mirror of `./scripts`

Same mirror discipline as for packages. Tests are organized into a small, fixed set of literal subdirectories — only `<pkg>` is variable, everything else is a literal name:

| Subdir | Tracked? | Mirrors / contains |
| :--- | :--- | :--- |
| `tests/scripts/` | ✅ | 1:1 mirror of `./scripts/` (the bulk of unit tests) |
| `tests/examples/` | ✅ | one `test_<example-stem>.py` per file in `./examples/` |
| `tests/agentic/` | ✅ | agentic-trigger tests — LLM invokes the skill / MCP tool / CLI and we assert the right path fires |
| `tests/integration/` | ✅ | cross-module / cross-package tests |
| `tests/e2e/` | ✅ | end-to-end pipeline tests (full `data → result` runs) |
| `tests/github_actions/` | ✅ | local GitHub Actions runner config (`act`/Apptainer) |
| `tests/coverage/` | gitignored | HTML / XML coverage reports |
| `tests/logs/` | gitignored | pytest run logs, captured stdout/stderr |
| `tests/reports/` | optional | agent-generated test summaries |

Test-file naming pattern (mirror with public/private prefix, double underscore for private):

```
scripts/path/to/run_pipeline.py            tests/scripts/path/to/test_run_pipeline.py
scripts/path/to/_helper.py                 tests/scripts/path/to/test__helper.py
```

Large/long tests should target a remote/HPC runner via `dev_test_hpc*` MCP tools rather than blocking local dev.

### `./config` — project-scope YAML tree

Centralized project parameters, loaded by `@stx.session` into `CONFIG`. **Scripts pull parameters from here rather than hardcoding.**

- One YAML per logical concern: `./config/PATH.yaml`, `./config/PARAMS.yaml`, `./config/EXPERIMENT.yaml`, `./config/COLORS.yaml`.
- `.gitkeep` so the directory exists even when empty.
- Resolution chain: **direct argument → CONFIG yaml → env var → default** (see [02_research-project_02_config-and-parameters.md](02_research-project_02_config-and-parameters.md) for full semantics).
- Logically separated YAMLs make it cheap to override one concern (e.g. swap `PARAMS.yaml` per experiment) without touching others.

### `./data` — input + intermediate data

- Project data files. Large files **gitignored**.
- Small files, `.gitkeep`, and symlinks may be tracked.
- Symlinks to artifacts are useful for navigating `./data/` as a centralized directory even when bytes live elsewhere (NAS, scratch, HPC scratch).
- Run outputs do **not** live here — those go under `SDIR_OUT/` (relative to the script that produced them).

### `./examples` — runnable demos

Same convention as for packages:

- Numbered: `./examples/01_<descriptive-name>.{py,sh,ipynb}`.
- `_out/` directory committed: `./examples/01_<descriptive-name>_out/`.
- `./examples/00_run_all.sh` dispatches everything.
- Each example matched by `./tests/examples/test_*.py`.
- Less common in research projects than in packages; but useful for showcasing how the project's pipelines are invoked.

### `./docs` — human-facing documentation

- README is the entry point; deeper docs go here (`./docs/installation.md`, `./docs/methods/<topic>.md`).
- Generated docs live in `./docs/_build/` (gitignored).
- `./docs/assets/` — figures, screenshots, diagrams referenced from README and other docs.
- `./docs/to_claude/` — agent context files (guidelines, hooks, examples). **Must be gitignored** — local-machine artifacts, not part of the shipped repo.
- `./GITIGNORED/` — catch-all file-based scratch channel.

## Hidden / scratch directories

| Dir | Use |
| --- | --- |
| `./.dev/` | Single scratch space — sandbox tests, parking-lot ideas, half-baked experiments. Gitignored. Organize by category subdir (`./.dev/<category>/`). **Promote** valuable code out (`→ scripts/`, `examples/`) or **prune** periodically. |
| `./.old/` | **Hide, don't delete** — keeps git history clean while removing visual noise. Acceptable to clear in a dedicated cleanup commit once nothing references it. |

## `SDIR_OUT` and `SDIR_RUN` — deterministic round-trips

`@stx.session` injects two path variables so save/load round-trips don't leak run-specific paths into your code:

- `SDIR_OUT` — *deterministic* output directory derived from the script's identity. Same script → same path → overwriteable. Use for figures, summaries, processed data the next run should clobber.
- `SDIR_RUN` — *unique* per-invocation directory (timestamp + run-id). Use for logs, full-state snapshots, anything you want to keep across reruns.

```python
stx.io.save(figure, SDIR_OUT / "summary.png")           # overwrites prior runs
stx.io.save(state, SDIR_RUN / "checkpoint.pkl")         # keeps every run
```

This is the canonical pattern that pairs with `./config/` and `./data/` to make experiments reproducible.

## Mirror discipline (mandatory)

`./scripts`, `./tests/scripts/`, and `./examples` mirror each other 1:1. Same load-bearing rule as for packages — a reader who knows where a pipeline lives in `./scripts/` finds its tests + demo without searching, CI deduces coverage gaps mechanically, and renames cascade predictably.

```
scripts/analysis/_helper.py
tests/scripts/analysis/test__helper.py     # private: double underscore
scripts/analysis/run_pipeline.py
tests/scripts/analysis/test_run_pipeline.py
examples/01_invoke_run_pipeline.py
tests/examples/test_01_invoke_run_pipeline.py
```

## What's allowed at the repo root

| File | Purpose |
| :--- | :--- |
| `README.md` | Primary entry point |
| `LICENSE` | License text |
| `pyproject.toml` | Even research projects use `pyproject.toml` for dev-deps + Makefile-driven tooling (no `setup.py`, `requirements.txt`) |
| `Makefile` | Thin dispatcher; logic in `./scripts/` |
| `.gitignore`, `.gitattributes` | VCS hygiene |
| `CLAUDE.md` (optional) | AI-agent context for this repo |

Everything else belongs in a subdirectory. **Do not create new top-level directories** without strong reason.

## Production-ready always

The main branch must be runnable **today**:

- Half-finished experiments live on a `feature/<verb>-<object>` branch.
- Obsolete files hidden under `.old/`, not littering visible paths.
- `./examples/` runs cleanly start-to-finish.
- Tests pass on `main`.
- README accurately describes current state, not aspirational state.

## Anti-patterns

- **Hardcoded parameters in scripts** — bypasses the `direct → CONFIG → env → default` chain; same value gets re-defined in three places, drifts.
- **Run outputs committed under `./data/`** — pollutes inputs with derived artifacts. Use `SDIR_OUT/` instead.
- **`./scripts/` that doesn't mirror `./tests/scripts/`** — coverage analysis becomes manual; renames break test discoverability.
- **Examples without `_out/`** — readers can't see what the demo produces without running it themselves.
- **`.dev/` with no categorization** — devolves into a junk drawer.
- **`.old/` that grows forever** — prune archives older than two release cycles.

## Pre-release / project-handoff checklist

- [ ] Every `scripts/.../*.py` has a corresponding `tests/scripts/.../test_*.py`
- [ ] Every example has a tracked `_out/` and `tests/examples/test_*.py`
- [ ] `./config/*.yaml` covers every parameter consumed by `./scripts/`
- [ ] `./data/` symlinks point at canonical sources; large files gitignored
- [ ] No half-finished work outside a `feature/*` branch
- [ ] No top-level files outside the allowed-at-root list
- [ ] `.dev/` has only categorized subdirs; nothing rotted >1 quarter
- [ ] `.old/` doesn't dominate any directory listing
- [ ] README reflects current behavior, not aspirational
- [ ] `make ci-local` (or equivalent) passes from a clean clone
