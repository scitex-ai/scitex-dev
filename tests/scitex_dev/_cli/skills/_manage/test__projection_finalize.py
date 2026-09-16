"""Tests for exporter-to-registry projection finalization."""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.skills._manage._helpers import _ensure_symlink
from scitex_dev._cli.skills._manage._projection_finalize import (
    finalize_projection,
    install_result_dict,
    registry_from_listing,
)
from scitex_dev.skill_registry import SCHEMA, audit_projection


def _source_listing(root: Path) -> dict[str, list[dict[str, str]]]:
    source = root / "source" / "example"
    source.mkdir(parents=True)
    skill_file = source / "SKILL.md"
    skill_file.write_text("# canonical\n", encoding="utf-8")
    return {
        "example": [
            {
                "path": str(skill_file),
                "rel_path": "SKILL.md",
            }
        ]
    }


def _copied_projection(root: Path) -> Path:
    projection = root / "projection"
    skill = projection / "example" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nversion: 1.0\n---\n# canonical\n", encoding="utf-8")
    return projection


def test_registry_from_export_listing_keeps_canonical_source(tmp_path: Path) -> None:
    # Arrange
    listed = _source_listing(tmp_path)

    # Act
    registry = registry_from_listing(listed)

    # Assert
    assert (
        registry.ok,
        registry.records[0].name,
        registry.records[0].path,
    ) == (True, "example", (tmp_path / "source" / "example").resolve())


def test_empty_export_listing_is_a_missing_source_finding() -> None:
    # Arrange
    listed = {}

    # Act
    registry = registry_from_listing(listed)

    # Assert
    assert [(finding.code, finding.kind) for finding in registry.issues] == [
        ("SI-100", "missing")
    ]


def test_finalize_writes_v2_manifest_and_accepts_transformed_copy(
    tmp_path: Path,
) -> None:
    # Arrange
    registry = registry_from_listing(_source_listing(tmp_path))
    projection = _copied_projection(tmp_path)

    # Act
    result = finalize_projection(registry, projection, "test-adapter")
    skill = result.manifest["skills"][0]

    # Assert
    assert (
        result.audit.ok,
        result.manifest_path.is_file(),
        result.manifest["schema_version"],
        skill["projection_hash"] != skill["source_hash"],
    ) == (True, True, SCHEMA, True)


def test_top_level_harness_symlink_audits_same_neutral_store(tmp_path: Path) -> None:
    # Arrange
    registry = registry_from_listing(_source_listing(tmp_path))
    projection = _copied_projection(tmp_path)
    finalize_projection(registry, projection, "test-adapter")
    harness_link = tmp_path / "claude" / "skills" / "scitex"

    # Act
    _ensure_symlink(harness_link, projection)
    audited = audit_projection(registry, harness_link)

    # Assert
    assert (audited.ok, harness_link.resolve()) == (True, projection.resolve())


def test_install_json_envelope_names_manifest_digest_and_findings(
    tmp_path: Path,
) -> None:
    # Arrange
    registry = registry_from_listing(_source_listing(tmp_path))
    projection = _copied_projection(tmp_path)
    finalized = finalize_projection(registry, projection, "test-adapter")

    # Act
    result = install_result_dict(
        finalized,
        {"example": [projection / "example" / "SKILL.md"]},
        projection,
    )

    # Assert
    assert (
        result["schema_version"],
        result["projection_sha256"].startswith("sha256:"),
        result["manifest"],
        result["findings"],
        result["ok"],
    ) == (
        SCHEMA,
        True,
        str(projection / ".scitex-skills.json"),
        [],
        True,
    )


def test_source_change_after_copy_is_reported_stale(tmp_path: Path) -> None:
    # Arrange
    listed = _source_listing(tmp_path)
    registry = registry_from_listing(listed)
    projection = _copied_projection(tmp_path)
    finalize_projection(registry, projection, "test-adapter")
    Path(listed["example"][0]["path"]).write_text("# changed\n", encoding="utf-8")

    # Act
    changed_registry = registry_from_listing(listed)
    audited = audit_projection(changed_registry, projection)

    # Assert
    assert {(finding.code, finding.kind) for finding in audited.issues} == {
        ("SP-404", "stale")
    }


def test_projection_change_after_manifest_is_reported_stale(tmp_path: Path) -> None:
    # Arrange
    registry = registry_from_listing(_source_listing(tmp_path))
    projection = _copied_projection(tmp_path)
    finalize_projection(registry, projection, "test-adapter")
    (projection / "example" / "SKILL.md").write_text(
        "# projection changed\n", encoding="utf-8"
    )

    # Act
    audited = audit_projection(registry, projection)

    # Assert
    assert {(finding.code, finding.kind) for finding in audited.issues} == {
        ("SP-402", "stale")
    }
