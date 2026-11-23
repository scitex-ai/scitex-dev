---
description: |
  [TOPIC] Harness-neutral skill discovery and projection validation
  [DETAILS] Package-local `_skills/<name>/` trees are authoritative; Claude, Codex, and Hermes directories are generated projections. Use `scitex_dev.skill_registry` to discover explicit package roots, hash sources, produce a versioned manifest, and report missing, broken, duplicate, obsolete, or stale projection entries. Use when building or checking a harness adapter. This documents implemented runtime behavior; a clean `audit_projection` result is relative to its supplied registry snapshot and manifest, not proof of live harness adoption or approved transformation semantics.
tags: [scitex-dev-skill-registry]
---

# Harness-neutral skill registry

The authority is each package's
`src/<import-name>/_skills/<skill-name>/` directory. A harness cache is a
projection, never a source. Do not repair package content by editing
`~/.claude`, a Codex skill directory, or a Hermes cache.

## Runtime contract

For installed discovery, `discover_installed_skills()` reads registered providers
from the interpreter running Dev and applies owner opt-outs. See
[12_config.md](12_config.md) for configuration and precedence. The explicit-root
API below is for source/harness adapters; it does not broaden installed discovery
to every checkout.

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

`RegistryReport` stores the source hashes computed during discovery.
`audit_projection` rereads projected content and the manifest; it does not
rediscover or rehash canonical source trees. Rediscover after source changes
before auditing. An unchanged copied projection can still pass against an old
report even after its canonical source has changed. A fresh report detects that
stale source stamp. Neither call locks source and projection against concurrent
changes, nor proves which skills an agent has loaded.

With `projection_root=...`, `projection_manifest_json` records the current
materialized tree hash. That supports added frontmatter, but also means a clean
audit does not establish that a transformation preserved skill meaning. Review
the adapter's transformation separately; do not restamp altered output merely
to clear a stale finding. `hash_skill_tree` hashes relative file names and bytes,
excluding `.git` and `__pycache__` path components; it is not a file-mode check.

The owning functions are in `skill_registry/_discover.py` and `_projection.py`.
Discovery, manifest and projection controls live in
`tests/scitex_dev/skill_registry/test___init__.py`; installed-provider controls
are in `test__installed.py` in that same test directory.

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
