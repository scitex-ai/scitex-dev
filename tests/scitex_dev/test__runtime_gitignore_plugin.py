"""PS-234 keeps runtime data local while shared configuration stays trackable."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess

import pytest

from scitex_dev._runtime_gitignore_plugin import (
    check_runtime_gitignore,
    check_runtime_registry_gitignore,
    get_plugin,
)


@dataclass
class RecordedViolation:
    rule: str
    where: str
    detail: str


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path, *, name: str = "project") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    return repo


def _runtime(
    repo: Path, *, root: str = ".scitex", package: str = "agent-container"
) -> Path:
    runtime = repo / root / package / "runtime"
    runtime.mkdir(parents=True)
    return runtime


def _seed(runtime: Path) -> None:
    for relative in ("run.json", ".hidden", "nested/deep/value.json", "nested/.hidden"):
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("host-local\n")


def _findings(repo: Path) -> list[RecordedViolation]:
    out: list[RecordedViolation] = []
    check_runtime_gitignore(repo, RecordedViolation, out)
    return out


def _registry_findings(root: Path) -> list[RecordedViolation]:
    out: list[RecordedViolation] = []
    check_runtime_registry_gitignore(root, RecordedViolation, out)
    return out


def _write_policy(runtime: Path, policy: str | None) -> None:
    if policy is not None:
        (runtime / ".gitignore").write_text(policy)


def test_plugin_registers_blocking_runtime_rule() -> None:
    # Arrange
    rule_id = "PS-234"
    # Act
    registered = get_plugin()["rules"]
    metadata = [(rule[0], rule[1], rule[3], rule[4]) for rule in registered]
    # Assert
    assert metadata == [(rule_id, "§4b", "E", "runtime-state-gitignored")]


def test_plugin_exposes_runtime_state_checker() -> None:
    # Arrange
    expected = [check_runtime_gitignore]
    # Act
    checks = get_plugin()["checks"]
    # Assert
    assert checks == expected


def test_plugin_exposes_explicit_registry_checker() -> None:
    # Arrange
    expected = [check_runtime_registry_gitignore]
    # Act
    checks = get_plugin()["registry_checks"]
    # Assert
    assert checks == expected


@pytest.mark.parametrize(
    "root, name", [(".scitex", "project"), ("src/.scitex", "project"), (".", ".scitex")]
)
def test_discovers_supported_state_tree_roots(
    tmp_path: Path, root: str, name: str
) -> None:
    # Arrange
    repo = _repo(tmp_path, name=name)
    _runtime(repo, root=root)
    # Act
    findings = _findings(repo)
    # Assert
    assert [finding.rule for finding in findings] == ["PS-234"]


@pytest.mark.parametrize(
    "package", ["agent-container", "logging", "dev", "arbitrary-package"]
)
def test_checks_runtime_for_every_package(tmp_path: Path, package: str) -> None:
    # Arrange
    repo = _repo(tmp_path)
    _runtime(repo, package=package)
    # Act
    findings = _findings(repo)
    # Assert
    assert [finding.rule for finding in findings] == ["PS-234"]


def test_absent_runtime_has_no_finding(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(tmp_path)
    config = repo / ".scitex" / "agent-container" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("shared: true\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert findings == []


@pytest.mark.parametrize(
    "policy", [None, "", "# Nothing ignored\n", "*.log\n", "cache/**\n", "/nested/**\n"]
)
def test_missing_or_selective_policies_are_refused(
    tmp_path: Path, policy: str | None
) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    _seed(runtime)
    _write_policy(runtime, policy)
    # Act
    findings = _findings(repo)
    # Assert
    assert [finding.rule for finding in findings] == ["PS-234"]


@pytest.mark.parametrize("pattern", ["*", "**", "/*", "/**", "**/*", "/**/*"])
def test_catch_all_covers_hidden_and_nested_contents(
    tmp_path: Path, pattern: str
) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    _seed(runtime)
    (runtime / ".gitignore").write_text(f"# Entire host-local tree\n{pattern}\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert findings == []


@pytest.mark.parametrize(
    "negation", ["!keep.json", "!nested/", "!nested/keep.json", "!.gitignore"]
)
def test_negations_after_final_catch_all_are_refused(
    tmp_path: Path, negation: str
) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    (runtime / ".gitignore").write_text(f"*\n{negation}\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert [finding.rule for finding in findings] == ["PS-234"]


@pytest.mark.parametrize(
    "policy", ["!keep.json\n*\n", "*\n!keep.json\n**\n", "*\n!nested/\n/**/*\n"]
)
def test_later_catch_all_overrides_earlier_negations(
    tmp_path: Path, policy: str
) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    _seed(runtime)
    (runtime / ".gitignore").write_text(policy)
    # Act
    findings = _findings(repo)
    # Assert
    assert findings == []


@pytest.mark.parametrize(
    "relative", ["run.json", ".hidden", "nested/value.json", ".gitignore"]
)
@pytest.mark.parametrize(
    "root, name", [(".scitex", "project"), ("src/.scitex", "project"), (".", ".scitex")]
)
def test_indexed_runtime_entries_remain_refused_after_ignore(
    tmp_path: Path, relative: str, root: str, name: str
) -> None:
    # Arrange
    repo = _repo(tmp_path, name=name)
    runtime = _runtime(repo, root=root)
    tracked = runtime / relative
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("host-local\n")
    _git(repo, "add", "--", str(tracked.relative_to(repo)))
    (runtime / ".gitignore").write_text("*\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


@pytest.mark.parametrize(
    "root, name", [(".scitex", "project"), ("src/.scitex", "project"), (".", ".scitex")]
)
def test_deleted_indexed_runtime_entry_is_still_refused(
    tmp_path: Path, root: str, name: str
) -> None:
    # Arrange
    repo = _repo(tmp_path, name=name)
    runtime = _runtime(repo, root=root)
    tracked = runtime / "deleted.json"
    tracked.write_text("host-local\n")
    _git(repo, "add", "--", str(tracked.relative_to(repo)))
    tracked.unlink()
    (runtime / ".gitignore").write_text("*\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_deleted_runtime_directory_is_detected_from_index(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    tracked = runtime / "deleted.json"
    tracked.write_text("host-local\n")
    _git(repo, "add", "--", str(tracked.relative_to(repo)))
    tracked.unlink()
    runtime.rmdir()
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


@pytest.mark.parametrize("relative", ["config.yaml", "spec.yaml", "host.json"])
def test_indexed_config_outside_runtime_remains_allowed(
    tmp_path: Path, relative: str
) -> None:
    # Arrange
    repo = _repo(tmp_path)
    runtime = _runtime(repo)
    (runtime / ".gitignore").write_text("*\n")
    config = runtime.parent / relative
    config.write_text("shared: true\n")
    _git(repo, "add", "--", str(config.relative_to(repo)))
    # Act
    findings = _findings(repo)
    # Assert
    assert findings == []


def _linked_runtime(
    tmp_path: Path, *, parent_policy: str | None, leaf_policy: str | None = "*\n"
) -> tuple[Path, Path]:
    repo = _repo(tmp_path)
    owner = repo / ".scitex" / "agent-container"
    owner.mkdir(parents=True)
    target = tmp_path / "host-runtime"
    target.mkdir()
    _seed(target)
    if leaf_policy is not None:
        (target / ".gitignore").write_text(leaf_policy)
    runtime = owner / "runtime"
    runtime.symlink_to(target, target_is_directory=True)
    if parent_policy is not None:
        (owner / ".gitignore").write_text(parent_policy)
    return repo, runtime


def test_runtime_symlink_cannot_ignore_itself(tmp_path: Path) -> None:
    # Arrange
    repo, _runtime_path = _linked_runtime(tmp_path, parent_policy=None)
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_directory_only_pattern_does_not_cover_symlink(tmp_path: Path) -> None:
    # Arrange
    repo, _runtime_path = _linked_runtime(tmp_path, parent_policy="runtime/\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_ignored_runtime_symlink_checks_target_policy(tmp_path: Path) -> None:
    # Arrange
    repo, _runtime_path = _linked_runtime(tmp_path, parent_policy="runtime\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert findings == []


@pytest.mark.parametrize("leaf_policy", [None, "", "*.log\n", "*\n!keep.json\n"])
def test_ignored_runtime_symlink_rejects_invalid_target_policy(
    tmp_path: Path, leaf_policy: str | None
) -> None:
    # Arrange
    repo, _runtime_path = _linked_runtime(
        tmp_path, parent_policy="runtime\n", leaf_policy=leaf_policy
    )
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_broken_runtime_symlink_is_not_silently_skipped(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(tmp_path)
    owner = repo / ".scitex" / "agent-container"
    owner.mkdir(parents=True)
    (owner / ".gitignore").write_text("runtime\n")
    (owner / "runtime").symlink_to(
        tmp_path / "missing-runtime", target_is_directory=True
    )
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_indexed_runtime_symlink_remains_refused_after_ignore(tmp_path: Path) -> None:
    # Arrange
    repo, runtime = _linked_runtime(tmp_path, parent_policy=None)
    _git(repo, "add", "--", str(runtime.relative_to(repo)))
    (runtime.parent / ".gitignore").write_text("runtime\n")
    # Act
    findings = _findings(repo)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def test_custom_registry_root_accepts_all_package_policies(tmp_path: Path) -> None:
    # Arrange
    registry = tmp_path / "custom-state-root"
    for package in ("agent-container", "logging", "arbitrary-package"):
        runtime = _runtime(registry, root=".", package=package)
        (runtime / ".gitignore").write_text("*\n")
    # Act
    findings = _registry_findings(registry)
    # Assert
    assert findings == []


def test_custom_registry_root_reports_every_missing_policy(tmp_path: Path) -> None:
    # Arrange
    registry = tmp_path / "custom-state-root"
    runtimes = [
        _runtime(registry, root=".", package=package)
        for package in ("agent-container", "logging")
    ]
    expected = {str(runtime / ".gitignore") for runtime in runtimes}
    # Act
    findings = _registry_findings(registry)
    # Assert
    assert {finding.where for finding in findings} == expected


def test_explicit_registry_does_not_search_nested_project_roots(tmp_path: Path) -> None:
    # Arrange
    registry = tmp_path / "custom-state-root"
    runtime = _runtime(registry, root=".")
    (runtime / ".gitignore").write_text("*\n")
    for decoy in (".scitex", "src/.scitex", "project/.scitex", "home/.scitex"):
        _runtime(registry, root=decoy, package="foreign-package")
    # Act
    findings = _registry_findings(registry)
    # Assert
    assert findings == []


@contextmanager
def _registry_environment(root: Path):
    prior = os.environ.get("SCITEX_DIR")
    os.environ["SCITEX_DIR"] = str(root)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("SCITEX_DIR", None)
        else:
            os.environ["SCITEX_DIR"] = prior


def test_explicit_registry_does_not_consult_environment_root(tmp_path: Path) -> None:
    # Arrange
    registry = tmp_path / "selected-state"
    runtime = _runtime(registry, root=".")
    (runtime / ".gitignore").write_text("*\n")
    other_registry = tmp_path / "other-state"
    _runtime(other_registry, root=".")
    # Act
    with _registry_environment(other_registry):
        findings = _registry_findings(registry)
    # Assert
    assert findings == []


def test_registry_subdirectory_detects_indexed_runtime_paths(tmp_path: Path) -> None:
    # Arrange
    repo = _repo(tmp_path, name="dotfiles")
    registry = repo / "src" / "custom-state-root"
    runtime = _runtime(registry, root=".")
    tracked = runtime / "host-state.json"
    tracked.write_text("host-local\n")
    _git(repo, "add", "--", str(tracked.relative_to(repo)))
    (runtime / ".gitignore").write_text("*\n")
    # Act
    findings = _registry_findings(registry)
    # Assert
    assert any(finding.rule == "PS-234" for finding in findings)


def _registry_runtime_symlink(tmp_path: Path) -> tuple[Path, Path]:
    repo = _repo(tmp_path, name="dotfiles")
    registry = repo / "src" / "custom-state-root"
    owner = registry / "agent-container"
    owner.mkdir(parents=True)
    (owner / ".gitignore").write_text("runtime\n")
    target = tmp_path / "host-runtime"
    target.mkdir()
    (target / ".gitignore").write_text("*\n")
    (owner / "runtime").symlink_to(target, target_is_directory=True)
    return repo, registry


def test_registry_subdirectory_accepts_ignored_external_runtime_symlink(
    tmp_path: Path,
) -> None:
    # Arrange
    _repo_path, registry = _registry_runtime_symlink(tmp_path)
    # Act
    findings = _registry_findings(registry)
    # Assert
    assert findings == []


def test_symlinked_registry_accepts_ignored_external_runtime_symlink(
    tmp_path: Path,
) -> None:
    # Arrange
    _repo_path, registry = _registry_runtime_symlink(tmp_path)
    alias = tmp_path / "selected-state-root"
    alias.symlink_to(registry, target_is_directory=True)
    # Act
    findings = _registry_findings(alias)
    # Assert
    assert findings == []
