---
description: |
  [TOPIC] Ecosystem Local State — Roots & Resolution
  [DETAILS] The two `.scitex/<pkg-short>/` roots (project tracked/runtime + user tracked/runtime) with project-overrides-user precedence, the mandatory `runtime/` subdirectory and its `.gitkeep`+`README.md` seeds + `.gitignore` shape, the `.scitex/dev/config.yaml` tracked-not-gitignored exception, the `<pkg-short>` prefix-stripping rule, the CLI-flag→env→project→user precedence chain with the `$SCITEX_DIR` note, and §3.5 lazy-mkdir (never via pip-install hooks; `PS-146`). Part of the `06_dot_scitex_directory.md` local-state layout. Use when deciding WHERE a package writes and HOW that path resolves.
tags: [scitex-general-ecosystem-local-state-roots]
---

# Local State — Roots & Resolution

The two roots, `<pkg-short>` naming, the precedence chain, and lazy
directory creation. Part of the local-state layout
([06_dot_scitex_directory.md](06_dot_scitex_directory.md)).

## 1. The two roots

Every scope carries two parallel trees — one **tracked** (rules / config the team commits) and one **runtime-only** (outputs / logs / caches that must not enter git):

| Precedence | Scope | Root | Example (`scitex-scholar`) | Tracked by git? |
|---|---|---|---|---|
| higher | **Project (tracked)** | `<project-root>/.scitex/<pkg-short>/` | `./.scitex/scholar/` | Yes — config.yaml, custom dicts, skill bundles |
| higher | **Project (runtime)** | `<project-root>/.scitex/<pkg-short>/runtime/` | `./.scitex/scholar/runtime/` | No — only `.gitkeep` + `README.md` committed |
| lower | **User (tracked)** | `~/.scitex/<pkg-short>/` | `~/.scitex/scholar/` | Yes (inside dotfiles repo, if the user versions their home) |
| lower | **User (runtime)** | `~/.scitex/<pkg-short>/runtime/` | `~/.scitex/scholar/runtime/` | No |

**Project scope always wins.** A package reads project-local state if present and only falls back to the user root when the project file does not exist. CLI flags and env vars override both — see §3.

### The `runtime/` subdirectory

Every `<pkg-short>/` root **MUST** contain a `runtime/` subdirectory. This is where the package writes everything that is re-creatable from config + source: logs, PID files, cached downloads, temporary workspaces, SQLite databases, dashboard state, etc.

`runtime/` is intentionally ignored by git. Each package ships two seed files and nothing else:

```
<pkg-short>/runtime/
├── .gitkeep        # Committed so the directory exists in fresh clones
└── README.md       # Committed, one paragraph explaining what lives here
                    #   and pointing at the local-state-directories skill
```

The package's `.gitignore` contains a single line that excludes everything *except* those two files:

```gitignore
# <project-root>/.gitignore (or a nested one inside the package root)
.scitex/*/runtime/*
!.scitex/*/runtime/.gitkeep
!.scitex/*/runtime/README.md
```

Rationale: the dir must exist on first clone (so `PathManager` doesn't have to `mkdir` and accidentally expose permission bugs), but its *contents* must never leak — they are per-host, per-run, often large, and sometimes sensitive. Seeing `runtime/` appear in a `git status` is an immediate signal that something wrote where it shouldn't, or that `.gitignore` was not set up.

### `.scitex/dev/config.yaml` — tracked, not gitignored

The audit-tool config (`<repo>/.scitex/dev/config.yaml` — root
whitelist for `audit-project`) MUST travel with the repo, otherwise CI
applies a different whitelist than local and audit results diverge
mysteriously. Use file-level exclusion under `.scitex/` so the
negation rule applies (a `.scitex/` dir-level exclusion blocks
negation):

```gitignore
# <project-root>/.gitignore
.scitex/*
!.scitex/dev/
.scitex/dev/*
!.scitex/dev/config.yaml
```

Incident 2026-05-11: a scitex-io codecov.yml PS-103 violation kept
firing in CI even after local whitelist was added, because the entire
`.scitex/` directory was gitignored and the negation never reached the
config file.

## 2. `<pkg-short>` — prefix-stripping rule

`<pkg-short>` is the package name with the `scitex-` prefix removed. Packages that don't carry the prefix use their name as-is.

| Package (pip name) | `<pkg-short>` | Local root |
|---|---|---|
| `scitex-dev` | `dev` | `~/.scitex/dev/` |
| `scitex-scholar` | `scholar` | `~/.scitex/scholar/` |
| `scitex-orochi` | `orochi` | `~/.scitex/orochi/` |
| `scitex-clew` | `clew` | `~/.scitex/clew/` |
| `scitex-cloud` | `cloud` | `~/.scitex/cloud/` |
| `scitex-writer` | `writer` | `~/.scitex/writer/` |
| `scitex-linter` | `linter` | `~/.scitex/linter/` |
| `figrecipe` | `figrecipe` | `~/.scitex/figrecipe/` |
| `crossref-local` | `crossref-local` | `~/.scitex/crossref-local/` |
| `openalex-local` | `openalex-local` | `~/.scitex/openalex-local/` |

## 3. Precedence chain (highest first)

Applies uniformly to config file resolution; packages may extend it to state files when user overrides are sensible.

| # | Source | Example |
|---|---|---|
| 1 | CLI flag | `--config <path>` |
| 2 | Env var | `$SCITEX_<PKG>_CONFIG` |
| 3 | Project scope | `<project>/.scitex/<pkg-short>/config.yaml` |
| 4 | User scope | `~/.scitex/<pkg-short>/config.yaml` |

**Note on `$SCITEX_DIR`.** `SCITEX_DIR` is *not* a step in this chain — it **transforms the meaning of the user-scope root** (step 4). Setting `SCITEX_DIR=/mnt/fast-ssd/scitex` makes `~/.scitex/<pkg-short>/` resolve to `/mnt/fast-ssd/scitex/<pkg-short>/` everywhere. See §6.

## 3.5. Auto-creation: lazy mkdir, never via pip-install hooks

`pip install <pkg>` must **not** create `~/.scitex/<pkg-short>/` or any
of its sub-directories. Reasons:

1. Modern Python packaging (`pyproject.toml` + hatchling/setuptools)
   has no clean post-install hook; using setuptools `cmdclass` to
   bolt one on is fragile and breaks `pip install --user` /
   wheel-only installs.
2. CI runners and container builds run `pip install` in fresh
   environments; touching `~/.scitex/` there is unwanted side-effect
   pollution. Wheels should be inert.
3. `$SCITEX_DIR` relocation (§6) breaks if the package hardcodes
   `~/.scitex/...` at install time instead of resolving at runtime.

**Required pattern**: every code path that writes inside
`~/.scitex/<pkg-short>/` calls `mkdir(parents=True, exist_ok=True)`
on the immediate parent before writing. `PathManager` (§7) bakes this
in. A separate `<pkg> init` command may exist for users who want an
explicit "seed everything now" step, but it is never the ONLY way to
populate the directory.

```python
# YES — lazy, $SCITEX_DIR-aware, idempotent
def _ensure_cache_dir() -> Path:
    p = path_manager.get_cache_dir()  # resolves SCITEX_DIR / scope chain
    p.mkdir(parents=True, exist_ok=True)
    return p

# NO — install-time side effect, no $SCITEX_DIR awareness
# in setup.py / pyproject.toml [tool.hatch.build.hooks]
def post_install():
    Path("~/.scitex/scholar/cache").expanduser().mkdir(parents=True, exist_ok=True)
```

The `runtime/.gitkeep` and `runtime/README.md` seed files (§4b) ship
inside the **wheel** under `src/<import>/templates/runtime/` and are
materialised by `PathManager` on first use, not by an install hook.

**Audit — `PS-146 local-state-pip-install-side-effect`**: parses
`pyproject.toml` for hatch `[tool.hatch.build.hooks.<name>]` entries
whose hook script contains a `Path.home() / .scitex/...` mkdir, and
flags setuptools `cmdclass` overriding `install`/`develop`. Severity
`E` (hard fail) — the rule is unambiguous and the fix is mechanical.
