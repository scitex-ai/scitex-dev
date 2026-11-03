---
description: |
  [TOPIC] Skill distribution and update mechanics
  [DETAILS] Installed leaf skill discovery, canonical user store, editable links and optional Claude projection. Source remains in each leaf package.
tags: [scitex-dev-distribution]
---

# Skill distribution and update

Leaf packages ship their skill resources and register discovery providers. The
installed resources are the source for projection; generated state belongs
outside Git authority checkouts.

```bash
scitex-dev dev skills list --package scitex-dev --json
scitex-dev dev skills install --package scitex-dev --claude-symlink --dry-run --json
```

Review the plan; omit `--dry-run` to install into `~/.scitex/dev/skills/`.
`--dest` selects another external directory. `--claude-symlink` projects the
store through `~/.claude/skills/scitex`; it does not grant client approval or
prove the client loaded the skills. `--link` links editable source resources.
`--clean` removes package subdirectories before export, so use it deliberately.
Existing real content at the projection link is not overwritten.

The installer writes `.scitex-skills.json`, finalizes the registry, and audits
the projection before reporting success. A dry run lists resources without
copying or proving the eventual installed projection. There are no canonical
`skills update` or `skills upgrade` subcommands; rerun `dev skills install`.

Source: `_cli/skills/_manage/_install_cmd.py`, `_projection_finalize.py` and
`skill_registry/`. See [36_skill-registry.md](36_skill-registry.md) for hashes
and harness-neutral validation, and [39_interface-audit.md](39_interface-audit.md)
for the distinction between discovery, installation and client execution.
