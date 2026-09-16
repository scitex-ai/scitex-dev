"""Projection manifest and drift validation shared by agent harness adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import scitex_logging as slogging

from ._discover import hash_skill_tree
from ._model import RegistryIssue, RegistryReport, SkillRecord, sort_issues

_logger = slogging.getLogger(__name__)
MANIFEST_NAME = ".scitex-skills.json"
SCHEMA = "scitex-skills-projection/2"
_ADAPTER_FILES = {MANIFEST_NAME, "SKILL.md"}


class ProjectionManifestError(ValueError):
    """Raised when a projection claims a manifest that violates the schema."""


def _projection_digest(skills: list[dict[str, str]]) -> str:
    payload = json.dumps(skills, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_projection_manifest(
    records: Iterable[SkillRecord],
    adapter: str,
    *,
    projection_root: Path | None = None,
) -> dict[str, Any]:
    """Build deterministic data for a thin Claude, Codex, or Hermes adapter."""

    if not adapter.strip():
        raise ValueError("adapter must be a non-empty name")
    skills = []
    for item in sorted(
        records, key=lambda value: (value.name, value.owner, str(value.path))
    ):
        projection_hash = item.source_hash
        if projection_root is not None:
            projection_hash = hash_skill_tree(projection_root / item.name)
        skills.append(
            {
                "name": item.name,
                "owner": item.owner,
                "source": str(item.path),
                "source_hash": item.source_hash,
                "projection_hash": projection_hash,
            }
        )
    names = [item["name"] for item in skills]
    if len(names) != len(set(names)):
        raise ProjectionManifestError("cannot project duplicate skill names")
    return {
        "schema_version": SCHEMA,
        "adapter": adapter,
        "projection_sha256": _projection_digest(skills),
        "skills": skills,
    }


def projection_manifest_json(
    records: Iterable[SkillRecord],
    adapter: str,
    *,
    projection_root: Path | None = None,
) -> str:
    """Serialize a manifest byte-for-byte deterministically."""

    document = build_projection_manifest(
        records, adapter, projection_root=projection_root
    )
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _load_manifest(path: Path) -> dict[str, dict[str, str]] | None:
    manifest_path = path / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectionManifestError(f"cannot read {manifest_path}: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA:
        raise ProjectionManifestError(
            f"{manifest_path} does not declare schema {SCHEMA!r}"
        )
    if not isinstance(document.get("adapter"), str) or not document["adapter"].strip():
        raise ProjectionManifestError(f"{manifest_path} has no non-empty adapter")
    projection_sha256 = document.get("projection_sha256")
    if not isinstance(projection_sha256, str) or not projection_sha256.startswith(
        "sha256:"
    ):
        raise ProjectionManifestError(
            f"{manifest_path} has no sha256 projection digest"
        )
    skills = document.get("skills")
    if not isinstance(skills, list):
        raise ProjectionManifestError(f"{manifest_path} skills must be a list")
    indexed: dict[str, dict[str, str]] = {}
    required = {"name", "owner", "source", "source_hash", "projection_hash"}
    for index, raw in enumerate(skills):
        if not isinstance(raw, dict) or set(raw) != required:
            raise ProjectionManifestError(
                f"{manifest_path} skills[{index}] must contain exactly "
                f"{sorted(required)}"
            )
        if not all(isinstance(raw[key], str) and raw[key] for key in required):
            raise ProjectionManifestError(
                f"{manifest_path} skills[{index}] has an empty field"
            )
        name = raw["name"]
        if name in indexed:
            raise ProjectionManifestError(f"{manifest_path} repeats skill {name!r}")
        indexed[name] = raw
    if projection_sha256 != _projection_digest(list(skills)):
        raise ProjectionManifestError(
            f"{manifest_path} projection_sha256 does not match its skill records"
        )
    return indexed


def audit_projection(registry: RegistryReport, projection_root: Path) -> RegistryReport:
    """Compare a harness projection with canonical registry records.

    This function is read-only. It accepts symlinks or byte-identical copied
    trees and reports missing, broken, duplicate-target, obsolete, and stale
    entries. A malformed manifest raises instead of being silently ignored.
    """

    issues = list(registry.issues)
    if not projection_root.is_dir():
        issues.append(
            RegistryIssue(
                "SP-101",
                "missing",
                "*",
                projection_root,
                "projection root does not exist or is not a directory",
            )
        )
        return RegistryReport(registry.records, sort_issues(issues))

    manifest = _load_manifest(projection_root)
    if manifest is None:
        issues.append(
            RegistryIssue(
                "SP-401",
                "stale",
                "*",
                projection_root / MANIFEST_NAME,
                "projection has no source-hash manifest",
            )
        )
        manifest = {}

    unique_sources = {item.name: item for item in registry.records}
    duplicate_names = {
        issue.name for issue in registry.issues if issue.kind == "duplicate"
    }
    for name in duplicate_names:
        unique_sources.pop(name, None)

    entries = {
        item.name: item
        for item in projection_root.iterdir()
        if item.name not in _ADAPTER_FILES
    }
    resolved_targets: dict[Path, list[tuple[str, Path]]] = {}
    for name, entry in entries.items():
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            resolved_targets.setdefault(entry.resolve(), []).append((name, entry))
    for name, source in unique_sources.items():
        entry = entries.get(name)
        if entry is None:
            issues.append(
                RegistryIssue(
                    "SP-102",
                    "missing",
                    name,
                    projection_root / name,
                    "skill has no projection",
                )
            )
            continue
        if not entry.is_dir() or not (entry / "SKILL.md").is_file():
            issues.append(
                RegistryIssue(
                    "SP-201",
                    "broken",
                    name,
                    entry,
                    "projection target is unavailable or has no regular SKILL.md",
                )
            )
            continue
        projected_hash = hash_skill_tree(entry)
        stamp = manifest.get(name)
        expected_projection_hash = (
            stamp["projection_hash"] if stamp is not None else source.source_hash
        )
        if projected_hash != expected_projection_hash:
            issues.append(
                RegistryIssue(
                    "SP-402",
                    "stale",
                    name,
                    entry,
                    "projected content hash differs from its manifest record",
                )
            )
        if stamp is None:
            issues.append(
                RegistryIssue(
                    "SP-403",
                    "stale",
                    name,
                    entry,
                    "projection has no source-hash record",
                )
            )
        elif (
            stamp["owner"] != source.owner
            or Path(stamp["source"]) != source.path
            or stamp["source_hash"] != source.source_hash
        ):
            issues.append(
                RegistryIssue(
                    "SP-404",
                    "stale",
                    name,
                    entry,
                    "source-hash record does not match the registry",
                )
            )

    for name, entry in sorted(entries.items()):
        if name not in unique_sources and name not in duplicate_names:
            issues.append(
                RegistryIssue(
                    "SP-301",
                    "obsolete",
                    name,
                    entry,
                    "projection has no canonical source",
                )
            )
    for name in sorted(set(manifest) - set(unique_sources)):
        issues.append(
            RegistryIssue(
                "SP-302",
                "obsolete",
                name,
                projection_root / MANIFEST_NAME,
                "manifest record has no canonical source",
            )
        )
    for matches in resolved_targets.values():
        if len(matches) > 1:
            for name, entry in matches:
                issues.append(
                    RegistryIssue(
                        "SP-202",
                        "duplicate",
                        name,
                        entry,
                        "multiple projection names resolve to the same target",
                    )
                )

    result = RegistryReport(registry.records, sort_issues(issues))
    _logger.debug(
        "audited projection %s: %d records, %d findings",
        projection_root,
        len(result.records),
        len(result.issues),
    )
    return result


__all__ = [
    "MANIFEST_NAME",
    "ProjectionManifestError",
    "SCHEMA",
    "audit_projection",
    "build_projection_manifest",
    "projection_manifest_json",
]
