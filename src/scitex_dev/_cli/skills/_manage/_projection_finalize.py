"""Bridge the legacy exporter to the harness-neutral projection registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ....skill_registry import (
    MANIFEST_NAME,
    SCHEMA,
    RegistryIssue,
    RegistryReport,
    SkillRecord,
    audit_projection,
    hash_skill_tree,
    write_projection_manifest,
)


@dataclass(frozen=True)
class ProjectionFinalizeResult:
    """Installer-facing result of manifest persistence and postcondition audit."""

    registry: RegistryReport
    audit: RegistryReport
    manifest_path: Path | None
    manifest: dict[str, object] | None


def registry_from_listing(
    listed: Mapping[str, Sequence[Mapping[str, str]]],
) -> RegistryReport:
    """Convert the exporter's source listing to authoritative records."""

    records: list[SkillRecord] = []
    issues: list[RegistryIssue] = []
    if not listed:
        issues.append(
            RegistryIssue(
                "SI-100",
                "missing",
                "*",
                Path("."),
                "export discovery returned no skill namespaces",
            )
        )
    for name, entries in sorted(listed.items()):
        skill_entries = [
            entry for entry in entries if entry.get("rel_path") == "SKILL.md"
        ]
        if not skill_entries:
            skill_entries = [
                entry
                for entry in entries
                if not entry.get("rel_path")
                and Path(entry.get("path", "")).name == "SKILL.md"
            ]
        if len(skill_entries) != 1:
            issues.append(
                RegistryIssue(
                    "SI-101",
                    "broken",
                    name,
                    Path(skill_entries[0]["path"]) if skill_entries else Path(name),
                    "export source must contain exactly one SKILL.md",
                )
            )
            continue
        skill_file = Path(skill_entries[0]["path"])
        source_root = skill_file.parent
        if not source_root.is_dir() or not skill_file.is_file():
            issues.append(
                RegistryIssue(
                    "SI-102",
                    "broken",
                    name,
                    source_root,
                    "export source is unavailable or SKILL.md is not regular",
                )
            )
            continue
        records.append(
            SkillRecord(
                name=name,
                owner=name,
                path=source_root.resolve(strict=True),
                skill_file=skill_file.resolve(strict=True),
                source_hash=hash_skill_tree(source_root),
            )
        )
    return RegistryReport(tuple(records), tuple(issues))


def registry_from_projection(
    exported: Mapping[str, Sequence[Path]], projection_root: Path
) -> RegistryReport:
    """Describe a PyPI projection when its extraction directory is ephemeral."""

    listed = {
        name: [
            {
                "path": str(projection_root / name / "SKILL.md"),
                "rel_path": "SKILL.md",
            }
        ]
        for name in exported
    }
    return registry_from_listing(listed)


def finalize_projection(
    registry: RegistryReport, projection_root: Path, adapter: str
) -> ProjectionFinalizeResult:
    """Persist a manifest atomically, then audit the materialized projection."""

    if not registry.ok:
        return ProjectionFinalizeResult(registry, registry, None, None)
    manifest_path, manifest = write_projection_manifest(
        registry.records, adapter, projection_root
    )
    audited = audit_projection(registry, projection_root)
    return ProjectionFinalizeResult(registry, audited, manifest_path, manifest)


def install_result_dict(
    finalized: ProjectionFinalizeResult,
    exported: Mapping[str, Sequence[Path]],
    destination: Path,
    *,
    claude_projection: Path | None = None,
    additional_findings: Sequence[RegistryIssue] = (),
) -> dict[str, Any]:
    """Build the single stable JSON object emitted by ``skills install``."""

    findings = [*finalized.audit.issues, *additional_findings]
    return {
        "schema_version": SCHEMA,
        "projection_sha256": (
            finalized.manifest.get("projection_sha256")
            if finalized.manifest is not None
            else None
        ),
        "manifest": str(finalized.manifest_path or destination / MANIFEST_NAME),
        "destination": str(destination),
        "claude_projection": (
            str(claude_projection) if claude_projection is not None else None
        ),
        "packages": {
            name: [str(path) for path in paths]
            for name, paths in sorted(exported.items())
        },
        "findings": [finding.to_dict() for finding in findings],
        "ok": not findings,
    }


__all__ = [
    "ProjectionFinalizeResult",
    "finalize_projection",
    "install_result_dict",
    "registry_from_listing",
    "registry_from_projection",
]
