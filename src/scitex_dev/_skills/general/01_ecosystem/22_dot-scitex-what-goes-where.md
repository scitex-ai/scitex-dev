---
description: |
  [TOPIC] Ecosystem Local State — What Goes Where
  [DETAILS] §4 of the local-state layout — the tracked-at-root (`<pkg-short>/`: config.yaml, cli-audit-dict.yaml, skill bundles, runtime seeds) vs runtime-only (`runtime/`: logs, PID files, cache, workspace, DBs, `containers/*.sif`, host-built `bin/`) split; the `~/.scitex/<pkg>/{containers,bin}` ecosystem convention; and §4c the interactive-REPL output cache under `runtime/cache/` honouring `$SCITEX_DIR`. Part of `06_dot_scitex_directory.md`. Use when deciding whether a file the package writes is tracked config or regenerable runtime.
tags: [scitex-general-ecosystem-local-state-what-goes-where]
---

# Local State — What Goes Where

The tracked-vs-runtime split at each `<pkg-short>/` root. Part of the
local-state layout ([06_dot_scitex_directory.md](06_dot_scitex_directory.md)).

## 4. What goes where

The package root splits into **tracked** (top-level) and **runtime** (under `runtime/`). The split is the same at both project and user scope.

### 4a. Tracked at the root (`<pkg-short>/`)

Intent: declarative inputs — things the team commits and reviews.

| File / subdir | Purpose |
|---|---|
| `config.yaml` | Primary config (canonical name — always `config.yaml`, never `<pkg>_config.yaml`) |
| `cli-audit-dict.yaml` | Per-scope linter custom dict (see `03_interface/02_cli/07_audit-cli.md` §1d) |
| `shared/skills/<pkg>-private/` | Private skill bundle (see `03_interface/04_skills/06_public-vs-private.md`) |
| `runtime/.gitkeep` | Marker so the runtime dir exists in fresh clones |
| `runtime/README.md` | One-paragraph notice explaining why `runtime/` is empty |

### 4b. Runtime-only (`<pkg-short>/runtime/`)

Intent: regenerable outputs — things each host / each run writes for itself, never to be committed.

| File / subdir | Purpose |
|---|---|
| `dashboard.log`, `*.log` | Logs |
| `dashboard.pid`, `*.pid` | PID files for background services |
| `cache/` | Derived / regenerable data |
| `workspace/` | Long-lived package-specific scratch (browser profiles, build outputs) |
| `*.db`, `*.sqlite` | Small embedded DBs (larger ones may relocate with `SCITEX_DIR`) |
| `export/` | Outputs of `scitex-dev skills export` and similar one-shot generators |
| `containers/` | Per-package container images (`*.sif`, `*.tar`). Large, per-host, regenerable from the `*.def` source under §4a. Never peer-rsync'd; gitignored under `runtime/`. |
| `bin/` | Host-specific built wrappers / launcher scripts (e.g. ones that hardcode the resolved overlay path). The **shipped, tracked** wrapper sources live at `<pkg-short>/bin/` under §4a — see the footnote below. |

Subdirectory layout within `runtime/` is up to each package, but **no per-package state may live outside its own root**.

> **`containers/` + `bin/` — `~/.scitex/<pkg>/{containers,bin}` ecosystem convention.** Per the cross-package agreement (Task #29 on the lead board): every package that ships an Apptainer / Singularity image standardises on `<pkg-short>/containers/*.sif` (under `runtime/`, this row) for the *built* image, and `<pkg-short>/bin/<verb>_<noun>.sh` for the *source* wrappers (tracked, see §4a). The split makes peer-rsync of `~/.scitex/` carry exactly the bin scripts (small, version-controllable) without dragging the multi-gigabyte container blobs (rebuildable from the `*.def`). See §4d for a worked example of what this looks like under a dotfiles-tracked `~/.scitex/`.

### 4c. Interactive REPL output cache (`runtime/cache/`)

Packages that auto-route user file output based on caller context (the
canonical example is `scitex_io.save()`) hit a special case when the
caller is an interactive REPL, IPython kernel, or `python -i` — there
is no script file to anchor a sibling `_out/` directory to. The
convention adopted 2026-05 is to write to:

```
$SCITEX_DIR/<pkg-short>/runtime/cache/<path>
```

defaulting to `~/.scitex/<pkg-short>/runtime/cache/<path>` when
`$SCITEX_DIR` is unset.

**Why under `runtime/cache/`** — these writes are regenerable, not
configuration, and they pollute fast (every interactive `save()`
produces a file). `cache/` is the explicit ephemeral bucket per §4b.

**Why honour `$SCITEX_DIR`** — interactive output volume can be large;
relocating the whole user-scope tree with `SCITEX_DIR=/mnt/fast-ssd/scitex`
must also relocate the REPL cache.

**Required pattern** in source code:

```python
import os as _os

def _interactive_cache_dir(pkg_short: str) -> str:
    base = _os.environ.get(
        "SCITEX_DIR",
        _os.path.join(_os.path.expanduser("~"), ".scitex"),
    )
    sdir = _os.path.join(base, pkg_short, "runtime", "cache")
    _os.makedirs(sdir, exist_ok=True)   # lazy mkdir per §3.5
    return sdir
```

**Reference implementation:** `scitex_io._save.save()` (the IPython /
`<stdin>` / `env_type in {"ipython", "interactive"}` branch). Pattern
applies to any future package that auto-routes outputs based on caller
context — e.g., a hypothetical `scitex_plt.save_fig()` should follow
the same rule and write to `~/.scitex/plt/runtime/cache/` when called
interactively.

This is distinct from `~/.scitex/<pkg-short>/cache/` (without `runtime/`),
which §5 forbids — the canonical bucket is always under `runtime/`.
