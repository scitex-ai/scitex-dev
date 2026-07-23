---
description: |
  [TOPIC] Ecosystem Local State Directories
  [DETAILS] Canonical filesystem layout for every scitex-* package's local state — config, logs, caches, PID files, workspace dirs. Two roots (`<project>/.scitex/<pkg-short>/` and `~/.scitex/<pkg-short>/`), project overrides user, always via PathManager.
tags: [scitex-general-ecosystem-local-state-directories]
---

# Local State Directories — Canonical Layout

Every `scitex-*` package that writes anything to disk — config, logs, caches, PID files, databases, workspace dirs — must put it under exactly one of two roots. Same dirname at both scopes, project overrides user, mirrors Claude Code's `~/.claude/` vs `<project>/.claude/`.

## Sections

- [21_dot-scitex-roots-and-resolution.md](21_dot-scitex-roots-and-resolution.md) — §1 the two roots + `runtime/` subdir + `.scitex/dev/config.yaml` exception, §2 `<pkg-short>` prefix-stripping, §3 precedence chain + `$SCITEX_DIR` note, §3.5 lazy mkdir (never via pip-install hooks; `PS-146`)
- [22_dot-scitex-what-goes-where.md](22_dot-scitex-what-goes-where.md) — §4 tracked-at-root (`<pkg-short>/`) vs runtime-only (`runtime/`), the `{containers,bin}` convention, §4c interactive-REPL output cache
- [23_dot-scitex-dotfiles-worked-example.md](23_dot-scitex-dotfiles-worked-example.md) — §4d CONFIG-vs-RUNTIME split on a dotfiles-tracked `~/.scitex/`, the `.gitignore` shape, peer-sync honesty
- [24_dot-scitex-relocation-and-pathmanager.md](24_dot-scitex-relocation-and-pathmanager.md) — §5 forbidden locations, §6 `$SCITEX_DIR` relocation, §7 always via `PathManager`, §8 legacy-layout migration
- [25_dot-scitex-cross-package-soc.md](25_dot-scitex-cross-package-soc.md) — §9 each package owns a domain (machine-identity example), §9.5 plugin-port pattern (`PS-145`)

## 10. Related

- `03_interface/02_cli/12_config-and-env.md` §6b — config-file resolution uses this layout.
- `01_ecosystem/03_modules-and-standalone-packages.md` §5–§6 — `PathManager` dependency-injection pattern.
- `01_ecosystem/04_environment-variables.md` — `SCITEX_DIR` and per-package `SCITEX_<PKG>_CONFIG`.
- `01_ecosystem/17_config-layout-enforcement.md` — **PS-222**, the mechanical rule enforcing §4a/§4b's tracked-vs-`runtime/` split on disk.
- `03_interface/04_skills/06_public-vs-private.md` — private skills live under `<pkg-short>/shared/skills/`.
- `scitex-resource` `_machine.py` — reference implementation of cross-package SoC (machine identity).

## 11. Quick Checklist (local-state directories)

- [ ] Every disk write goes under `<project>/.scitex/<pkg-short>/` or `~/.scitex/<pkg-short>/` — nowhere else.
- [ ] `<pkg-short>` is the pip name with the `scitex-` prefix stripped (e.g. `scitex-dev` → `dev`); non-prefixed packages use their bare name.
- [ ] Primary config file is named `config.yaml`; never `<pkg>_config.yaml`, never `<pkg>.yaml`.
- [ ] `<pkg-short>/runtime/` exists with `.gitkeep` + `README.md` committed; everything else under it gitignored.
- [ ] `.gitignore` exempts `.gitkeep` and `README.md` inside `runtime/` (`!.scitex/*/runtime/.gitkeep`, `!.scitex/*/runtime/README.md`).
- [ ] All paths resolve through `PathManager` — no `Path.home() / ".scitex/..."` literals in source.
- [ ] No writes to forbidden locations (`~/.cache/scitex/`, `~/.config/scitex/`, `~/.<pkg>/`, `./.scitex/<pkg>.yaml`, `/tmp/scitex-<pkg>-*`).
- [ ] **`pip install <pkg>` does not create `~/.scitex/<pkg-short>/`** (no post-install hooks, no setuptools cmdclass mkdir). Directory is created lazily on first write — see §3.5.
- [ ] **No writes or reads outside the package's own tree** — `~/.scitex/<other-pkg>/...` literals and `SCITEX_<OTHER>_*` env-var reads are forbidden in source. Use the plugin-port pattern (§9.5) for downstream extensibility.
- [ ] Setting `SCITEX_DIR=/some/other/path` relocates *every* user-scope read/write — verified by smoke test.
- [ ] Project scope is always a directory (`<project>/.scitex/<pkg-short>/`), never a single file at `<project>/.scitex/<pkg>.yaml`.
- [ ] If the package consumes another package's domain fact (machine name, SLURM cluster, …), it imports that package's API rather than re-deriving the answer.
- [ ] Migration shims from legacy paths are time-boxed (one minor version) — no permanent back-compat read paths.
- [ ] **Shell-completion install** writes a cache file under `~/.scitex/<pkg-short>/runtime/completion/<binary>` and a source line in the user's rc — never an `eval "$(_<PKG>_COMPLETE=...)"` line that re-invokes the binary on every shell start. See `03_interface/02_cli/03_required-introspection-commands.md`.
