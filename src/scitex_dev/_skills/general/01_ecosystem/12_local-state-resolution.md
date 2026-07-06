---
description: |
  [TOPIC] Ecosystem Local-State Resolution — config vs data vs runtime
  [DETAILS] Every scitex-* package resolves its on-disk state through the single canonical helper `scitex_config._ecosystem.local_state`, choosing the resolver by DATA NATURE: `path()` for config (project may shadow user), `user_path()` for DATA/STATE stores (user-canonical, never project-shadowed — the anti-footgun rule), `runtime_path()` for ephemera. Covers the `$SCITEX_DIR` relocator, the no-rolled-own-resolver mandate (audit PS-182), and the scitex-todo tasks.yaml shadowing incident.
tags: [scitex-general-ecosystem-local-state-resolution]
---

# Local-State Resolution — config vs data vs runtime

`06_dot_scitex_directory.md` defines the on-disk *layout* (`<project>/.scitex/<pkg>/` and `~/.scitex/<pkg>/`, the `runtime/` split, `$SCITEX_DIR`). This leaf defines *how a package resolves a path into that layout* — through one canonical helper, choosing the resolver **by the nature of the data**.

The single rule: **never roll your own precedence walk.** Use `scitex_config._ecosystem.local_state`. Which function you call is decided by whether the thing on disk is CONFIG, DATA/STATE, or RUNTIME.

## 1. The canonical helper

```python
from scitex_config._ecosystem import local_state
```

| Function | Resolves to | Project scope shadows user? |
|---|---|---|
| `path(pkg, *parts)` | project file if it EXISTS, else `$SCITEX_DIR/<pkg>/...` | **Yes** (config override) |
| `user_path(pkg, *parts)` | always `$SCITEX_DIR/<pkg>/...` | **No** (skips the project walk) |
| `runtime_path(pkg, *parts)` | `<scope>/runtime/...` (seeds `.gitkeep`+`README.md`) | follows scope |
| `user_root()` | `$SCITEX_DIR` (default `~/.scitex`) | — |
| `find_project_scope(pkg)` | `<git-root>/.scitex/<pkg>/` or `None` | — |

`path()` walks up from cwd to the first `.git/` root and returns the project file **iff it exists**; otherwise the user file. `user_path()` deliberately skips that walk.

## 2. Resolve by data nature

| Nature | Meaning | Use | Why |
|---|---|---|---|
| **CONFIG** | declarative, may be project-overridden (`config.yaml`, custom dicts) | `path()` | a research project's `.scitex/dev/config.yaml` *should* override ecosystem defaults |
| **DATA / STATE** | the canonical mutable record (task stores, DBs, registries, ledgers) | `user_path()` | there is ONE true store; a stray project copy must never shadow it |
| **RUNTIME** | ephemeral (logs, PIDs, sockets, caches) | `runtime_path()` | per-host, per-run, regenerable; never tracked |

## 3. The anti-footgun rule

> **A DATA/STATE store is user-canonical. It is resolved with `user_path()` and is NEVER project-shadowed.**

CONFIG shadowing is a feature — a project overrides a default. Applying that same "project wins" rule to a *data store* is a footgun: a process whose cwd happens to sit inside a repo with a stale `<repo>/.scitex/<pkg>/` silently reads the wrong record.

**Incident (2026-07).** The scitex-todo board read a WEEK-STALE task store. Root cause: `scitex_todo/_paths.py` rolled its own precedence putting project scope ABOVE user scope for `tasks.yaml`. A process run with cwd inside `~/proj/scitex-todo` (which carried a stale `.scitex/todo/`) shadowed the canonical `~/.scitex/todo/tasks.yaml`. `tasks.yaml` is DATA, not config — it must resolve via `user_path()`, so project scope can never shadow it.

## 4. `$SCITEX_DIR` and explicit overrides

- **`$SCITEX_DIR`** (default `~/.scitex`) is the ecosystem-wide user-root relocator. `local_state.user_root()` reads it per call: set it once and every package's user scope moves atomically. It is NOT a per-call precedence step — it *is* the user root. There is no per-package `$SCITEX_<PKG>_DIR` root relocator; use the one `$SCITEX_DIR`.
- A package MAY expose one explicit-path override env var (e.g. `SCITEX_TODO_TASKS_YAML_SHARED`) that points at a specific store file. It layers as the **highest-precedence "explicit" step**, above the `local_state` resolution — an operator escape hatch, not a substitute for the helper.

Precedence for a DATA store, highest first: explicit arg → explicit-path env var → `user_path()` (`$SCITEX_DIR/<pkg>/...`).

## 5. Adoption mandate

Packages MUST resolve local state through `scitex_config._ecosystem.local_state`. Do NOT hand-roll a `_paths.py`/`paths.py` that re-implements the `.git`-root walk + `.scitex/<pkg>` precedence — that is how the incident above happened, and it drifts independently in every package that copies it.

**Audit — `PS-182 local-state-rolled-own-resolver`**: flags a `src/<pkg>/**/_paths.py` (or `paths.py`) that shows a git-root walk signal AND a `.scitex/<pkg>` project-scope literal but does NOT import `local_state`. Deterministic, warn-level during adoption. Fix by deleting the hand-rolled walk and calling `local_state.user_path()` / `path()` / `runtime_path()` per §2.

## 6. Worked example — the `user_path()` fix

```python
# BEFORE — rolled-own; project scope shadows user for a DATA store
def resolve_tasks_path() -> Path:
    git_root = _find_git_root(Path.cwd())              # own precedence
    if git_root and (git_root / ".scitex/todo/tasks.yaml").exists():
        return git_root / ".scitex/todo/tasks.yaml"    # shadows canonical
    return _user_root() / "tasks.yaml"

# AFTER — user-canonical via the helper; project scope can never shadow it
from scitex_config._ecosystem import local_state

def resolve_tasks_path() -> Path:
    return local_state.user_path("todo", "tasks.yaml")  # $SCITEX_DIR/todo/tasks.yaml
```

Config, by contrast, keeps `path()`:

```python
cfg = local_state.path("dev", "config.yaml")   # project .scitex/dev/config.yaml may override
```

## 7. Future refinement (b2)

PS-182 flags the *rolled-own resolver* (the root cause). A finer check — a resolution chain that orders project-scope ABOVE user-scope for a `.yaml`/`.db`/`.json` **data store specifically** — is deferred: detecting store-nature + chain-order cleanly enough to stay low-false-positive is a separate refinement. Ship b1; revisit b2 only with a low-false-positive design.

## Related

- `01_ecosystem/06_dot_scitex_directory.md` — the on-disk layout, `runtime/` split, forbidden locations, `PathManager`.
- `01_ecosystem/04_environment-variables.md` — `$SCITEX_DIR` and per-package `SCITEX_<PKG>_*`.
- `scitex_config._ecosystem._local_state` — the helper's reference implementation.
