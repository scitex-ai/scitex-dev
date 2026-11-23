# Harness-neutral skill registry

Package-local `src/<module>/_skills/<name>/` directories are the source of
truth. Claude, Codex, Hermes, and later harnesses consume projections; none is
an authority for skill content.

```python
from pathlib import Path

from scitex_dev.skill_registry import (
    audit_projection,
    discover_skills,
    projection_manifest_json,
)

registry = discover_skills({"scitex-example": Path("/srv/scitex-example")})
records = registry.require_valid()  # fail loud on missing/broken/duplicate sources
manifest = projection_manifest_json(records, adapter="codex")
audit = audit_projection(registry, Path("/configured/codex/skills/scitex"))
```

Adapters own only destination selection and materialization. They must retain
the registry names, create symlinks or deterministic copies, and write
`.scitex-skills.json` from `projection_manifest_json`. Schema v2 carries both
the canonical `source_hash` and materialized `projection_hash` because copied
exports may add version frontmatter. Its aggregate `projection_sha256` covers
both. Adapters must validate with `audit_projection` after generation. They
must not search a home directory
or fall back to another harness's cache when a configured source is absent.
The existing installer resolves its default neutral store through
`scitex_config._ecosystem.local_state.user_path("dev", "skills")` and rejects
any destination whose real path is inside a Git checkout. This guard includes
paths reached through a symlink such as `~/.scitex`; generated state must never
dirty an authority checkout.

`scitex-dev dev skills install` performs this finalization itself: it writes
the manifest with an atomic replace, audits the neutral destination, then (if
requested) installs and audits the top-level
`~/.claude/skills/scitex -> <neutral-store>` symlink. JSON success contains
`schema_version`, `projection_sha256`, `manifest`, and an empty `findings`
array. Any finding makes the command fail.

`RegistryReport.to_dict()` is the stable data boundary for CLI/MCP adapters.
Findings have a `kind` of `missing`, `broken`, `duplicate`, `obsolete`, or
`stale`; malformed manifests raise `ProjectionManifestError`. The tested
[manifest example](examples/skill-projection-manifest.json) is generated from
the same public API used by adapters, preventing an illustrative schema from
drifting away from runtime behavior.

## Interpret a clean audit within its snapshot

`discover_skills` computes each `SkillRecord.source_hash` once. The resulting
`RegistryReport` is a snapshot. `audit_projection` reads projected files and
the manifest against those supplied records; it does not rediscover canonical
sources. Rediscover after source edits before auditing. If a copied projection
and its manifest stay unchanged while source changes, the old report can still
produce no findings; the fresh report exposes the stale source stamp. These
calls do not lock trees against concurrent edits or inspect a running agent's
loaded skills.

Passing `projection_root` to `projection_manifest_json` hashes the materialized
output, allowing an adapter to add version frontmatter. The audit then checks
output against that recorded hash and source identity against the supplied
registry. It does not prove that the output's meaning matches its source or
approve arbitrary transformations. Review the adapter separately, and preserve
stale findings rather than restamping unexpected changes to make them pass.

`hash_skill_tree` hashes relative file names and contents while excluding files
under `.git` and `__pycache__` path components. File modes are not part of this
hash. The owning implementations are `skill_registry/_discover.py` and
`skill_registry/_projection.py`; the existing discovery, manifest, changed-copy,
symlink, duplicate and malformed-manifest controls are in
`tests/scitex_dev/skill_registry/test___init__.py`. These checks establish their
fixture scope, not current installed projections across the fleet.
