---
description: |
  [TOPIC] Ecosystem Local State — Dotfiles Worked Example
  [DETAILS] §4d — the CONFIG-vs-RUNTIME split made concrete on a dotfiles-tracked `~/.scitex/`: what's tracked (agents/*.yaml, account/usage metadata, secret path pointers, per-package config trees, `*.def` recipes, `bin/` wrapper sources) vs gitignored (all of `runtime/`, `*.sif` blobs, overlays/venvs, `.credentials.json`, per-account project state, session transcripts, verification.db); the dotfiles-side `.gitignore` shape with file-level negation; why the split keeps `stow`/`chezmoi`/`rsync` peer-sync honest; and the cross-linking anchor. Part of `06_dot_scitex_directory.md`. Use when versioning a home dir that tracks a curated subset of `~/.scitex/`.
tags: [scitex-general-ecosystem-local-state-dotfiles]
---

# Local State — Dotfiles Worked Example

The CONFIG-vs-RUNTIME split on a real dotfiles-tracked `~/.scitex/`. Part
of the local-state layout ([06_dot_scitex_directory.md](06_dot_scitex_directory.md)).

### 4d. Worked example — dotfiles-tracked `~/.scitex/`

The split is most visible (and most easily understood) when the user
puts their **home directory under `git`** and tracks a curated subset
of `~/.scitex/` inside that dotfiles repo. The tracked subset is the
**CONFIG** layer (shared across that user's machines); everything
under `runtime/` (per §4b) stays gitignored and is regenerated on each
host. This subsection shows what the split looks like on a real
dotfiles-tracked `~/.scitex/`.

#### What's tracked (CONFIG — committed into the dotfiles repo)

Each row below is a real example from a maintainer's `~/.dotfiles/src/.scitex/`:

| Path | Why tracked |
|---|---|
| `agents/*.yaml` | Agent specifications — the same agent should boot the same way on every machine the user owns. |
| `account.json`, `usage.json` | Per-user account metadata (which org, which usage profile). Same across the user's machines. |
| `secrets/bot-token` *(the path, not the value)* | The **location pointer** for the token; the *value* is per-host (see runtime side). Tracking the path keeps every machine looking in the same place. |
| `dev/config.yaml`, `dev/cli-audit-dict.yaml` | scitex-dev's own per-scope config (§4a). |
| `scholar-config/`, `todo/`, `writer/`, ... | Per-package config trees that are conceptually "the user's choices" rather than "this run's output". |
| `*.def` | Apptainer / Singularity image **definitions** — text recipes, small, peer-versionable. The **built** `*.sif` blobs go under `runtime/containers/` per §4b. |
| `<pkg-short>/bin/<verb>_<noun>.sh` | Source wrappers per the §4b footnote — verb-form names per the project-template convention. |

#### What's gitignored (RUNTIME — per-machine, regenerated locally)

| Path | Why **not** tracked |
|---|---|
| `<pkg-short>/runtime/` and every `*.log`, `*.pid`, `cache/`, `workspace/`, `*.db` underneath | Per §4b — regenerable, often large, sometimes sensitive (PID files give away process structure). |
| `<pkg-short>/runtime/containers/*.sif` | Per the §4b footnote — large blobs, rebuild from the `.def` source instead of peer-rsyncing. |
| `overlays/`, `venvs/`, `<pkg-short>/runtime/bin/` (the *built* wrapper variants) | Per-host filesystem reality (Python prefix, container overlay path, etc.) baked in at build time. |
| `.credentials.json` and its `.credentials.json.bak.*` rotations | Secrets. The *path* may be tracked at the parent (a `secrets/` pointer file), but the values are not. |
| `accounts/*/projects/` | Per-account project working state — large, churn-y, host-local. |
| `runtime/cache/` (per §4c REPL-output cache) and any package-specific subcache | Regenerable on demand. |
| `session-transcripts/`, agent runtime logs | High volume, low long-term value, often sensitive. |
| `verification.db` (clew / verifier local DB) | Per-machine session state; regenerable from inputs + pipeline rerun. |

#### Mechanical enforcement — the `.gitignore` shape on the dotfiles side

The pattern the user's dotfiles repo carries (rooted at the home-directory level so it owns `.scitex/`):

```gitignore
# In the dotfiles repo's root .gitignore (covers ~/.scitex/* by symlink or stow):

# Block every runtime/ subtree under any package
.scitex/*/runtime/
!.scitex/*/runtime/.gitkeep
!.scitex/*/runtime/README.md

# Block the secret-bearing files at the user root, keep the directory shape
.scitex/.credentials.json
.scitex/.credentials.json.bak.*
.scitex/secrets/*
!.scitex/secrets/.gitkeep
!.scitex/secrets/README.md

# Per-account project state — host-local
.scitex/accounts/*/projects/
```

The negation lines (`!`) follow the same file-level rule as §1 (the
`.scitex/dev/config.yaml` example): once a parent is excluded, only
file-level re-includes work — never a re-included subdir.

#### Why this matters for peer-sync (`stow` / `chezmoi` / `rsync -a ~/.scitex`)

The dotfiles repo is what the user fans out across machines. The
RUNTIME / CONFIG split is **how `git status` keeps the fan-out honest**:

- A new tracked file shows up → it propagates to every paired machine on next pull. Intentional.
- A `runtime/*.sif`, `*.db`, `*.log` shows up → `git status` ignores it. Stays on the host that built it.
- A `.credentials.json` regression — say a package accidentally writes it tracked-side — appears in `git status` immediately. Fail-loud.

Without the runtime/ subtree convention, every package would have to
ship its own per-host exclude rules, and a single missing rule leaks
session state, container blobs, or secrets into the dotfiles repo.
With it, `runtime/` is **the one rule** and the rest is mechanical.

#### Anchor for cross-linking

Per-host READMEs (e.g. `~/.dotfiles/README.md`, the per-machine notes
in `~/.dotfiles/src/.scitex/README.md`) link **here** rather than
duplicating the rationale: this skill is the single source of truth
for the CONFIG-vs-RUNTIME contract. The host README's job is to
enumerate **which paths this user tracks on this host** — concrete,
local, narrow. The contract that makes the enumeration mean anything
is this section.
