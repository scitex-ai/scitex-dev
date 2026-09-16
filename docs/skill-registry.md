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
the registry names, create either symlinks or byte-identical copied trees, and
write `.scitex-skills.json` from `projection_manifest_json`. The manifest has a
`schema_version`, aggregate `projection_sha256`, and each source-tree hash.
They must validate
with `audit_projection` after generation. They must not search a home directory
or fall back to another harness's cache when a configured source is absent.
The existing installer resolves its default neutral store through
`scitex_config._ecosystem.local_state.user_path("dev", "skills")` and rejects
any destination whose real path is inside a Git checkout. This guard includes
paths reached through a symlink such as `~/.scitex`; generated state must never
dirty an authority checkout.

`RegistryReport.to_dict()` is the stable data boundary for CLI/MCP adapters.
Findings have a `kind` of `missing`, `broken`, `duplicate`, `obsolete`, or
`stale`; malformed manifests raise `ProjectionManifestError`. The tested
[manifest example](examples/skill-projection-manifest.json) is generated from
the same public API used by adapters, preventing an illustrative schema from
drifting away from runtime behavior.
