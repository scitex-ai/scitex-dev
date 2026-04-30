---
name: interface-cli-config-env
description: SciTeX CLI config and env vars — SCITEX_<PKG>_* namespace, config.yaml precedence (--config > env > project > user).
user-invocable: false
tags: [scitex-python, scitex-general, cli]
---

# §6. Config + env vars

## §6a. Env var namespace

- All scitex-owned env vars **must** be `SCITEX_<PACKAGE>_*`.
- Bare package-name prefixes are forbidden.
- Out of scope: third-party tools (`POSTGRES_*`, `DJANGO_*`, `VITE_*`, `CI`, `PATH`).

### Adapter pattern for framework env vars

- Define the canonical value as `SCITEX_<PKG>_*`.
- Translate inside the framework's settings file.
- Never let framework names leak into SciTeX-owned code.

## §6b. Config file location

Precedence (highest first):

1. `--config PATH`
2. `$SCITEX_<PKG>_CONFIG`
3. `<project>/.scitex/<pkg-short>/config.yaml`
4. `~/.scitex/<pkg-short>/config.yaml`

### Notes

- Canonical filename is always `config.yaml`.
- Project scope overrides user scope.
- CLI flags and env vars override both.
- Full layout rule (two roots, prefix-stripping `scitex-dev` → `dev`, `SCITEX_DIR`, `PathManager`) lives in [`../01_ecosystem_06_local-state-directories.md`](../01_ecosystem_06_local-state-directories.md).
- Document the fallback order in `--help`.
