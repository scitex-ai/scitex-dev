---
description: |
  [TOPIC] Installation
  [DETAILS] Base runtime installation, declared all/dev/docs toolchains, editable installation and scoped CLI/MCP verification.
tags: [scitex-dev-installation]
---

# Installation

## Basic install

```bash
python -m pip install scitex-dev
```

Use a dedicated virtual environment and the same Python interpreter for
installation and verification. Release CI qualifies Python 3.11, 3.12 and 3.13;
the project's declared Python floor and dependency resolution are separate facts.

The base distribution includes the CLI and MCP runtime dependencies. The retired
`cli` and `mcp` extras do not enable these interfaces and must not be recommended.

## Development and documentation toolchains

```bash
python -m pip install 'scitex-dev[all]'
```

| Extra | Provides |
|---|---|
| `all` | Combined declared development and documentation dependencies |
| `dev` | Declared development and test dependencies |
| `docs` | Declared documentation build dependencies |

Use `dev` or `docs` when only that toolchain is needed. The distribution's
`Provides-Extra` metadata and source `pyproject.toml` are authoritative.

## Editable / dev install

```bash
git clone --branch develop https://github.com/scitex-ai/scitex-dev.git
cd scitex-dev
python -m pip install -e '.[dev]'
```

## Smoke verify

```bash
python -m scitex_dev --version
python -m scitex_dev --help
python -m scitex_dev mcp doctor --json
```

The version command reports the installed distribution version. MCP doctor
checks dependencies and catalog discovery; a successful catalog does not prove
client loading or protocol readiness. See [41_agent-setup.md](41_agent-setup.md)
for normalized setup manifests, explicit client configuration and skills.

## Troubleshooting

- **`scitex-dev: command not found`** — activate the intended environment or
  use its `python -m scitex_dev`. Check that environment's script directory is
  on `PATH`; installing a retired extra does not fix a different interpreter.
- **MCP dependency/import failure** — inspect the versions reported by
  `python -m scitex_dev mcp doctor --json`. Qualify a clean environment with
  normal dependency resolution instead of treating a bare import or existing
  version number as readiness.
- **Version mismatches across the ecosystem** — run
  `scitex-dev ecosystem validate-versions --dry-run` (see [13_versions.md](13_versions.md)).

See [02_quick-start.md](02_quick-start.md) for a guided first run.
