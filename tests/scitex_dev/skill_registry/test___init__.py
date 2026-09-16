"""Contract tests for the public harness-neutral skill registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev.skill_registry import (
    MANIFEST_NAME,
    ProjectionManifestError,
    RegistryReport,
    SkillRecord,
    SkillRegistryError,
    audit_projection,
    build_projection_manifest,
    discover_skills,
    hash_skill_tree,
    projection_manifest_json,
)


def _skill(repo: Path, name: str, content: str = "# Skill\n") -> Path:
    target = repo / "src" / "example_pkg" / "_skills" / name
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    return target


def _valid_registry(repo: Path, name: str = "example") -> RegistryReport:
    _skill(repo, name)
    report = discover_skills({"example-package": repo})
    report.require_valid()
    return report


def _write_manifest(projection: Path, report: RegistryReport) -> None:
    (projection / MANIFEST_NAME).write_text(
        projection_manifest_json(report.records, "test-harness"), encoding="utf-8"
    )


def test_discovery_is_sorted_and_hash_changes_with_source(tmp_path: Path) -> None:
    # Arrange
    repo = tmp_path / "repo"
    second = _skill(repo, "zeta")
    first = _skill(repo, "alpha")
    report = discover_skills({"owner": repo})
    old_hash = report.records[0].source_hash

    # Act
    (first / "guide.md").write_text("new guidance\n", encoding="utf-8")

    # Assert
    assert (
        [record.name for record in report.records],
        hash_skill_tree(first) != old_hash,
        hash_skill_tree(second).startswith("sha256:"),
    ) == (["alpha", "zeta"], True, True)


def test_discovery_reports_missing_broken_and_duplicate_candidates(
    tmp_path: Path,
) -> None:
    # Arrange
    missing_repo = tmp_path / "missing"
    first = tmp_path / "first"
    second = tmp_path / "second"
    _skill(first, "same")
    _skill(second, "same")
    invalid = first / "src" / "example_pkg" / "_skills" / "invalid"
    invalid.mkdir()
    broken = first / "src" / "example_pkg" / "_skills" / "broken"
    broken.symlink_to(tmp_path / "absent", target_is_directory=True)

    # Act
    report = discover_skills(
        {"missing": missing_repo, "first": first, "second": second}
    )

    # Assert
    assert [(issue.kind, issue.name) for issue in report.issues] == [
        ("broken", "broken"),
        ("broken", "invalid"),
        ("duplicate", "same"),
        ("duplicate", "same"),
        ("missing", "missing"),
    ]


def test_require_valid_fails_loud_on_registry_findings(tmp_path: Path) -> None:
    # Arrange
    report = discover_skills({"missing": tmp_path / "missing"})

    # Act
    # Assert
    with pytest.raises(SkillRegistryError, match="skill registry is invalid"):
        report.require_valid()


def test_discovery_reports_existing_repo_without_skills(tmp_path: Path) -> None:
    # Arrange
    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()

    # Act
    report = discover_skills({"empty-package": empty_repo})

    # Assert
    assert [(issue.code, issue.kind, issue.name) for issue in report.issues] == [
        ("SR-105", "missing", "empty-package")
    ]


def test_manifest_serialization_is_deterministic(tmp_path: Path) -> None:
    # Arrange
    record = _valid_registry(tmp_path / "repo").records[0]

    # Act
    first = projection_manifest_json([record], "codex")
    second = projection_manifest_json([record], "codex")

    # Assert
    assert first == second


def test_manifest_refuses_duplicate_names(tmp_path: Path) -> None:
    # Arrange
    first = _valid_registry(tmp_path / "first").records[0]
    duplicate = SkillRecord(
        first.name,
        "other",
        tmp_path / "other",
        tmp_path / "other/SKILL.md",
        "sha256:1",
    )

    # Act
    # Assert
    with pytest.raises(ProjectionManifestError, match="duplicate"):
        build_projection_manifest([first, duplicate], "codex")


def test_manifest_refuses_empty_adapter(tmp_path: Path) -> None:
    # Arrange
    record = _valid_registry(tmp_path / "repo").records[0]

    # Act
    # Assert
    with pytest.raises(ValueError, match="non-empty"):
        build_projection_manifest([record], " ")


def test_projection_accepts_current_symlink_with_hash_manifest(tmp_path: Path) -> None:
    # Arrange
    report = _valid_registry(tmp_path / "repo")
    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / "example").symlink_to(
        report.records[0].path, target_is_directory=True
    )
    _write_manifest(projection, report)

    # Act
    audited = audit_projection(report, projection)

    # Assert
    assert (audited.ok, audited.to_dict()["ok"]) == (True, True)


def test_projection_reports_all_drift_classes_deterministically(
    tmp_path: Path,
) -> None:
    # Arrange
    repo = tmp_path / "repo"
    _skill(repo, "missing")
    copied_source = _skill(repo, "copied")
    _skill(repo, "broken")
    report = discover_skills({"owner": repo})
    projection = tmp_path / "projection"
    projection.mkdir()
    copied = projection / "copied"
    copied.mkdir()
    (copied / "SKILL.md").write_text("outdated\n", encoding="utf-8")
    (projection / "broken").symlink_to(tmp_path / "gone", target_is_directory=True)
    obsolete = projection / "obsolete"
    obsolete.mkdir()
    (obsolete / "SKILL.md").write_text("# old\n", encoding="utf-8")

    # Act
    audited = audit_projection(report, projection)
    classes = {(issue.kind, issue.name) for issue in audited.issues}

    # Assert
    assert (
        ("missing", "missing") in classes,
        ("broken", "broken") in classes,
        ("obsolete", "obsolete") in classes,
        ("stale", "*") in classes,
        ("stale", "copied") in classes,
        hash_skill_tree(copied_source) != hash_skill_tree(copied),
    ) == (True, True, True, True, True, True)


def test_projection_reports_duplicate_target_and_obsolete_alias(tmp_path: Path) -> None:
    # Arrange
    report = _valid_registry(tmp_path / "repo")
    projection = tmp_path / "projection"
    projection.mkdir()
    source = report.records[0].path
    (projection / "example").symlink_to(source, target_is_directory=True)
    (projection / "alias").symlink_to(source, target_is_directory=True)
    _write_manifest(projection, report)

    # Act
    audited = audit_projection(report, projection)

    # Assert
    assert (
        {issue.name for issue in audited.issues if issue.kind == "duplicate"},
        {
            issue.name
            for issue in audited.issues
            if issue.kind == "obsolete"
        },
    ) == ({"alias", "example"}, {"alias"})


def test_malformed_manifest_fails_loud(tmp_path: Path) -> None:
    # Arrange
    report = _valid_registry(tmp_path / "repo")
    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / MANIFEST_NAME).write_text("{}\n", encoding="utf-8")

    # Act
    # Assert
    with pytest.raises(ProjectionManifestError, match="does not declare schema"):
        audit_projection(report, projection)


def test_documented_manifest_is_generated_by_public_api() -> None:
    # Arrange
    repo_root = Path(__file__).parents[3]
    records = [
        SkillRecord(
            name="scitex-example",
            owner="scitex-example",
            path=Path("/opt/scitex-example/src/scitex_example/_skills/scitex-example"),
            skill_file=Path(
                "/opt/scitex-example/src/scitex_example/_skills/"
                "scitex-example/SKILL.md"
            ),
            source_hash="sha256:0123456789abcdef",
        )
    ]
    fixture = repo_root / "docs" / "examples" / "skill-projection-manifest.json"

    # Act
    documented = json.loads(fixture.read_text(encoding="utf-8"))

    # Assert
    assert documented == build_projection_manifest(records, "codex")
