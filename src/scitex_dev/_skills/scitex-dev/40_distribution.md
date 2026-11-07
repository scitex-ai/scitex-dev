---
description: |
  [TOPIC] Skill distribution and update mechanics
  [DETAILS] Installed leaf skill discovery, canonical user store, explicit agent-readable directories and editable links. Source remains in each leaf package.
tags: [scitex-dev-distribution]
---

# Skill distribution and update

Leaf packages ship their skill resources and register discovery providers. The
installed resources are the source for projection; generated state belongs
outside Git authority checkouts.

```bash
scitex dev skills list --package scitex-dev --json
scitex dev skills install --package scitex-dev --dry-run --json
scitex dev skills install --package scitex-dev --directory /tmp/agent-skills --dry-run --json
```

Review the plan; omit `--dry-run` to install. Without `--directory`, the default
store is `~/.scitex/dev/skills/`. `--directory` selects an explicit external
location readable by any agent or tool; `--dest` remains a compatible alias.
The standalone bootstrap form is `scitex-dev dev skills install`. Older Dev
releases without `--directory` require `--dest`; inspect installed help first.

Select a single owning distribution with `--package`. Otherwise discovery uses
installed, reachable and enabled leaf providers in Dev's current environment.
See [12_config.md](12_config.md) for owner-level opt-outs and effective state;
installation does not enable disabled tools or override selection policy.

`--link` links editable source resources. `--clean` refreshes the requested
managed namespaces through the validated staging projection; foreign and
unselected content is preserved, and modified managed content is refused rather
than overwritten. The existing `--claude-symlink` option remains an explicit
compatibility convenience; it is not required for generic destinations.
Verify discovery and selected context through the consuming client separately
from file installation.

The installer writes `.scitex-skills.json`, finalizes the registry, and audits
the projection before reporting success. A dry run lists resources without
copying or proving the eventual installed projection. There are no canonical
`skills update` or `skills upgrade` subcommands; rerun `dev skills install`.

Source: `_cli/skills/_manage/_install_cmd.py`, `_projection_finalize.py` and
`skill_registry/`. See [36_skill-registry.md](36_skill-registry.md) for hashes
and harness-neutral validation, and [39_interface-audit.md](39_interface-audit.md)
for the distinction between discovery, installation and client execution.
