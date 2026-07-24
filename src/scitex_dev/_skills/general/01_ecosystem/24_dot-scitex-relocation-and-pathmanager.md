---
description: |
  [TOPIC] Ecosystem Local State — Relocation, PathManager & Forbidden Paths
  [DETAILS] §5 forbidden locations (`~/.cache/scitex/`, `~/.config/scitex/`, `~/.<pkg>/`, `./.scitex/<pkg>.yaml`, `/tmp/scitex-<pkg>-*`); §6 `$SCITEX_DIR` as the single ecosystem-wide user-scope relocation lever (project scope intentionally unaffected); §7 always resolve via `PathManager`, never hardcode `Path.home()/".scitex/..."`; §8 time-boxed migration from legacy layouts (one minor version, no permanent back-compat shims). Part of `06_dot_scitex_directory.md`. Use when relocating state, resolving a path in code, or migrating an old layout.
tags: [scitex-general-ecosystem-local-state-relocation]
---

# Local State — Relocation, PathManager & Forbidden Paths

Where NOT to write, how `$SCITEX_DIR` relocates the user scope, resolving
via `PathManager`, and migrating legacy layouts. Part of the local-state
layout ([06_dot_scitex_directory.md](06_dot_scitex_directory.md)).

## 5. Forbidden locations

Do **not** write to any of these — they fragment the layout and break `SCITEX_DIR` relocation:

- `~/.cache/scitex/…` — use `~/.scitex/<pkg-short>/cache/` instead
- `~/.config/scitex/…` — use `~/.scitex/<pkg-short>/config.yaml` instead
- `~/.<pkg>/` (tool's own dotdir at home) — always under `~/.scitex/`
- `./.scitex/<pkg>.yaml` — bare file in project root; use `<project>/.scitex/<pkg-short>/config.yaml` (the project scope is always a directory, never a single file)
- `/tmp/scitex-<pkg>-*` — use `~/.scitex/<pkg-short>/cache/` for transient state that must survive a reboot; `tempfile.TemporaryDirectory()` for ephemeral

## 6. `SCITEX_DIR` — ecosystem-wide relocation

`$SCITEX_DIR` (default `~/.scitex`) is the **single lever** that relocates the user scope atomically. Honouring this is the entire reason we use one shared root instead of per-package dotdirs.

```bash
export SCITEX_DIR=/mnt/fast-ssd/scitex
# Everything under ~/.scitex/* now lives at /mnt/fast-ssd/scitex/*
```

Project scope (`<project>/.scitex/`) is intentionally *not* affected by `SCITEX_DIR` — project state lives with the project.

## 7. Always via `PathManager`, never hardcode

```python
# NO
screenshot_dir = Path.home() / ".scitex/scholar/workspace/screenshots"

# YES
screenshot_dir = (
    ScholarConfig().path_manager.get_cache_engine_dir() / "workspace" / "screenshots"
)
```

Hardcoded paths break when users set `SCITEX_DIR` or the package moves to project scope. `PathManager` consults both scopes in precedence order and returns the resolved path. Child packages should **not** import an upstream package's config to find their own dirs — inject the path as a constructor argument instead (see `01_ecosystem/03_modules-and-standalone-packages.md` §5).

## 8. Migration from legacy layouts

If a package already ships a different layout (`~/.scitex/<pkg>_config.yaml`, `~/.cache/scitex/<pkg>/…`, etc.), migrate once:

1. Add the new location to `PathManager` as primary.
2. On first startup, `mv` old → new and emit a one-time deprecation warning to stderr.
3. Keep the fallback read-path for one minor version, then remove.

Do not keep permanent back-compat shims — legacy locations silently defeat `SCITEX_DIR`.
