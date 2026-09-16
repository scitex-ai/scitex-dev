"""Harness-neutral registry for package-local SciTeX skills.

Harness integrations are deliberately adapters: discover the canonical
package-local trees here, then project the returned records into Claude,
Codex, Hermes, or another consumer without embedding harness policy in the
domain layer.
"""

from ._discover import discover_skills, hash_skill_tree
from ._model import RegistryIssue, RegistryReport, SkillRecord, SkillRegistryError
from ._projection import (
    MANIFEST_NAME,
    SCHEMA,
    ProjectionManifestError,
    audit_projection,
    build_projection_manifest,
    projection_manifest_json,
)
from ._write import write_projection_manifest

__all__ = [
    "MANIFEST_NAME",
    "SCHEMA",
    "ProjectionManifestError",
    "RegistryIssue",
    "RegistryReport",
    "SkillRecord",
    "SkillRegistryError",
    "audit_projection",
    "build_projection_manifest",
    "discover_skills",
    "hash_skill_tree",
    "projection_manifest_json",
    "write_projection_manifest",
]
