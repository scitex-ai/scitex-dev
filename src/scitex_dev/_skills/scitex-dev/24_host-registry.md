---
description: |
  [TOPIC] Host registry
  [DETAILS] `scitex_dev.hosts` — the SciTeX-wide port answering "where is host X, and what's its ~/.scitex root?" (HostRecord, resolve, list_hosts), backed by ~/.scitex/dev/hosts.yaml, plus the `scitex-dev host list/show/resolve` CLI.
tags: [scitex-dev-host-registry]
---

# Host registry — `scitex_dev.hosts`

**Ports & Adapters.** `scitex_dev.hosts` is the **port**: the single
place that answers, ecosystem-wide, "where is host X, and what's its
`~/.scitex` root path?" Other packages — `sac`
(scitex-agent-container, which currently owns this ad hoc in
`~/.scitex/agent-container/config.yaml`), `scitex-hub`, and
`scitex-storage` — are the **adapters**: they call
`resolve()`/`list_hosts()` here instead of parsing their own host
config or hardcoding a host-specific path.

## Why this exists

A host-specific absolute path
(`/data/gpfs/projects/punim0264/ywatanabe/.scitex`, Spartan-only) was
committed as a literal git-tracked SYMLINK at `src/.scitex` in the
shared dotfiles repo. Every non-Spartan host that checks out that
commit gets a DANGLING symlink at `~/.scitex` — the path where the
ENTIRE fleet's config/runtime state lives — which already silently
broke config delivery to a NAS host. Resolving host paths through this
registry, rather than a hardcoded/symlinked path baked into version
control, is the fix.

## Python API

```python
from scitex_dev.hosts import resolve, list_hosts

spartan = resolve("spartan")
spartan.name           # "spartan"
spartan.kind           # "hpc-login"
spartan.ssh_alias      # "spartan" (None means local — no SSH hop)
spartan.scitex_root    # raw string, may contain ~
spartan.scitex_root_path  # expanded Path (expands on THIS process —
                          # see the property docstring for the
                          # "whose home directory" caveat on remotes)

for host in list_hosts():
    print(host.name, host.kind)
```

`HostRecord.kind` is one of `HOST_KINDS`: `workstation`, `hpc-login`,
`storage`. `resolve()` raises `UnknownHostError` (fail loud, no silent
fallback) with the full list of registered hosts and a remediation
pointing at the file to edit. `HostRegistryError` covers a malformed
`hosts.yaml` (bad shape, invalid `kind`, YAML parse error).

## Storage: `~/.scitex/dev/hosts.yaml`

A DATA/STATE store (see
`01_ecosystem/12_local-state-resolution.md`), resolved via
`local_state.user_path()` so it is never project-shadowed. Seeded with
the operator's known hosts (`ywata-note-win`, `spartan`, `nas`,
`nas1`, `nas2`, `mba`) on first use if it doesn't already exist.
Precedence (highest first): explicit `hosts_path=`/`--hosts-file` →
`$SCITEX_DEV_HOSTS_YAML` → the canonical user-scope file.

## CLI

```bash
scitex-dev host list                                    # table of every host
scitex-dev host list --json                              # structured JSON
scitex-dev host show spartan                              # full record
scitex-dev host resolve spartan --field scitex_root       # one field, for shell scripting

SPARTAN_ROOT=$(scitex-dev host resolve spartan --field scitex_root)
```

`host resolve --field` exits non-zero with an actionable stderr
message when the host isn't found — never a silent empty string.

## Scope note

This module ships only the registry. Migrating `sac` / `scitex-hub` /
`scitex-storage`'s own code to consume it is separate follow-up work
in each of those packages.

## Related

- [12_config.md](12_config.md) — `DevConfig`/`HostConfig` (a
  *different* concept: SSH targets for scitex-dev's own package-sync
  feature, unrelated to this ecosystem-wide host-path registry).
- `01_ecosystem/12_local-state-resolution.md` — the DATA/STATE vs
  CONFIG resolver rule this module follows.
