---
description: |
  [TOPIC] Agent knowledge setup
  [DETAILS] Leaf-owned MCP launch definitions, normalized JSON client configuration, installed skill discovery, and verified projections. Separate config installation, client loading and runtime readiness.
tags: [scitex-dev-agent-setup]
---

# Agent knowledge setup

Leaves own tools, launch definitions and skill resources. Dev supplies discovery,
manifest and projection primitives; SDK supplies Web contracts and GUI primitives.
A dispatcher must not maintain a second per-package inventory or silently choose
between conflicting declarations.

## Discover installed declarations

```bash
scitex-dev docs providers --json
scitex-dev dev skills list --package scitex-dev --json
scitex-dev dev skills get scitex-dev SKILL
```

`docs providers` reads `scitex_dev.docs` metadata without loading consumer code.
Its versioned JSON reports ambiguous names and explicitly says declarations are
not verified live endpoints. Python consumers use `list_doc_providers()`; rows
include canonical distribution names, targets, versions and summaries, not host
paths. Keep missing providers and duplicate ownership visible in browser views.

## MCP setup

```bash
scitex-dev mcp install --json
scitex-dev mcp install --config /tmp/owned-mcp.json --dry-run --json
```

Without `--config`, installation is informational. With an explicit compatible
JSON client file, omit `--dry-run` to merge. The normalized fragment is
`client_config.mcpServers`. The older `mcp_servers` key remains a compatibility
alias for Dev clients. No default client file is modified.

The shared Python primitives are `build_mcp_install_manifest` and
`install_mcp_client_config` in `scitex_dev.mcp_setup`. A leaf supplies its own
package, executable, argument vector and verification commands once. Do not infer
an executable or `mcp start` path from a distribution name: current leaf paths
still differ. These primitives do not load credentials or launch tools.

Config merge preserves foreign settings, refuses a conflicting same-name server
and invalid/symlink destinations, and reports no existing values. Writes use a
same-directory atomic replacement and a persistent per-file lock. Writers using
this installer serialize; other editors must coordinate to exclude all races.
Dry runs create neither config, parent directory nor lock. This JSON adapter is
not a universal installer for every client's TOML/YAML or approval format.

```bash
scitex-dev mcp doctor --json
scitex-dev mcp list-tools --json
```

Doctor returns nonzero for dependency/import or empty-catalog failures. A catalog
check does not establish that a client loaded or authorized the server. Qualify
stdio separately with initialize and tools/list before claiming protocol readiness;
stdout must carry protocol JSON, while diagnostics go to stderr. Business tool
execution needs its own appropriate tests.

## Skills setup

```bash
scitex-dev dev skills install --package scitex-dev --claude-symlink --dry-run --json
```

The canonical store is `~/.scitex/dev/skills/`. Leaf resources remain authoritative;
the store and harness directories are projections. Use the existing
`scitex_dev.skill_registry` hashes and `audit_projection`, not another registry.
Review the plan, then omit `--dry-run` to install. Inspect actual installed help
for supported projection and source options; a source checkout does not upgrade
a different installed wheel.

SAC's Hermes profile materializer already discovers installed enabled skill
providers, applies opt-outs/exclusions and audits the staged projection. That is
a separate runtime adapter, not proof that a manual install or a running profile
is current. Preserve each consumer's opt-outs and qualify its actual profile.

Adapters that require the protected installer must check
`scitex_dev.skill_registry.INSTALL_CAPABILITIES` for
`transactional-projection-v1` before invoking it in the same interpreter.
A version string or the existence of an older `skills install` command does
not establish this capability.

Record installed package versions, config/projection results, client load and
runtime checks separately. Do not report empty or unresolved discovery as a
successful installation.
