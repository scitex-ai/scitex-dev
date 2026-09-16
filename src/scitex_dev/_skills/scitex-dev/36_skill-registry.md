---
description: |
  [TOPIC] Harness-neutral skill discovery and projection validation
  [DETAILS] Package-local `_skills/<name>/` trees are authoritative; Claude, Codex, and Hermes directories are generated projections. Use `scitex_dev.skill_registry` to discover explicit package roots, hash sources, produce a versioned manifest, and report missing, broken, duplicate, obsolete, or stale projection entries. Use when building or checking a harness adapter. This documents implemented runtime behavior; it does not claim that a projection is current until `audit_projection` returns an empty finding set.
tags: [scitex-dev-skill-registry]
---

# Harness-neutral skill registry

The authority is each package's
`src/<import-name>/_skills/<skill-name>/` directory. A harness cache is a
projection, never a source. Do not repair package content by editing
`~/.claude`, a Codex skill directory, or a Hermes cache.

## Runtime contract

```python
from pathlib import Path

from scitex_dev.skill_registry import audit_projection, discover_skills

registry = discover_skills({"scitex-io": Path("/srv/scitex-io")})
records = registry.require_valid()
projection = audit_projection(registry, Path("/configured/harness/skills"))
```

Discovery roots are explicit. The runtime does not fall back from an absent
checkout to an installed distribution or another harness's cache. A candidate
must be a directory and contain a regular `SKILL.md`. Duplicate names remain
findings instead of being resolved by arbitrary traversal order.

Each generated projection carries `.scitex-skills.json` with
`schema_version`, an aggregate `projection_sha256`, and per-source and
materialized-projection hashes. Separate hashes allow deterministic copied
exports to add version frontmatter without concealing later source drift.
`audit_projection` accepts symlinks or byte-identical copies and reports five
finding classes: `missing`, `broken`, `duplicate`, `obsolete`, and `stale`.
A malformed claimed manifest raises `ProjectionManifestError`.

## Adapter boundary

Claude, Codex, and Hermes adapters choose only their destination and the
minimal materialization format. They consume `SkillRecord` / `RegistryReport`
or `to_dict()` and must validate after generation. Harness-specific discovery
syntax does not enter the registry domain.

The `skills install` command atomically writes the manifest, audits the neutral
store, and audits the optional top-level Claude symlink before reporting
success. It also rejects any output destination
whose resolved path lies inside a Git checkout. This includes a seemingly
user-local `~/.scitex` symlink that resolves into tracked dotfiles. A generated
cache must not dirty its authority checkout.
