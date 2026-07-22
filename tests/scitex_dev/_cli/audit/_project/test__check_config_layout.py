# -*- coding: utf-8 -*-
"""Tests for `_check_config_layout.py` (PS-222).

Convention (`_skills/general/01_ecosystem/06_dot_scitex_directory.md`):
everything directly under `.scitex/<pkg-short>/` is TRACKED except
`runtime/`, which is the one gitignored subdirectory; the primary config is
always named `config.yaml`; a package scope is always a DIRECTORY.

Every test builds a REAL git repository in a temp dir and REALLY runs
`git check-ignore` through the check (no mocks, no monkeypatched
subprocess) — the rule's whole substance is "what does git think", so
stubbing git would test nothing.

`test_ps222_stays_silent_for_gitignored_runtime_dir` is the CONTROL ARM: a
mutation that makes the check flag EVERYTHING must turn it red. Without it,
"flag everything" would look green across the rest of the file.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_config_layout import (
    check_ps222_config_layout,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


class _StubConfig:
    """Minimal ProjectConfig stand-in exposing the exemption surface."""

    def __init__(self, accepted=(), errors=()):
        self._accepted = set(accepted)
        self.exemption_errors = tuple(errors)

    def exemption_for(self, rule: str, rel_path: str, line: int):
        return (rule, rel_path, line) in self._accepted or None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


def _run(repo: Path, config=None) -> list:
    out: list = []
    check_ps222_config_layout(repo, _StubViolation, out, config=config)
    return out


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real, initialised git repo with an empty `.scitex/dev/` scope."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".scitex" / "dev").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def repo_canonical(repo: Path) -> Path:
    """The canonical shape: a tracked `.scitex/dev/config.yaml`."""
    (repo / ".scitex/dev/config.yaml").write_text("audit: {}\n", encoding="utf-8")
    _git(repo, "add", ".scitex/dev/config.yaml")
    return repo


@pytest.fixture
def repo_runtime_ignored(repo: Path) -> Path:
    """Canonical config PLUS a correctly-gitignored `runtime/` holding state."""
    (repo / ".scitex/dev/config.yaml").write_text("audit: {}\n", encoding="utf-8")
    runtime = repo / ".scitex/dev/runtime"
    runtime.mkdir()
    (runtime / "dashboard.log").write_text("noise\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".scitex/*/runtime/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", ".scitex/dev/config.yaml")
    return repo


@pytest.fixture
def repo_alias(repo: Path) -> Path:
    """A deprecated `<pkg-short>.yaml` primary-config alias."""
    (repo / ".scitex/dev/dev.yaml").write_text("audit: {}\n", encoding="utf-8")
    _git(repo, "add", ".scitex/dev/dev.yaml")
    return repo


@pytest.fixture
def repo_alias_underscore(repo: Path) -> Path:
    """A deprecated `<pkg-short>_config.yaml` primary-config alias."""
    (repo / ".scitex/dev/dev_config.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(repo, "add", ".scitex/dev/dev_config.yaml")
    return repo


@pytest.fixture
def repo_ignored_dir(repo: Path) -> Path:
    """A gitignored non-`runtime/` DIRECTORY under the package scope."""
    cache = repo / ".scitex/dev/cache"
    cache.mkdir()
    (cache / "blob.bin").write_text("x", encoding="utf-8")
    (repo / ".gitignore").write_text(".scitex/dev/cache/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    return repo


@pytest.fixture
def repo_ignored_file(repo: Path) -> Path:
    """A gitignored non-`runtime/` FILE beside the canonical config."""
    (repo / ".scitex/dev/config.yaml").write_text("audit: {}\n", encoding="utf-8")
    (repo / ".scitex/dev/secrets.yaml").write_text("k: v\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".scitex/dev/secrets.yaml\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", ".scitex/dev/config.yaml")
    return repo


@pytest.fixture
def repo_bare_file(repo: Path) -> Path:
    """The forbidden bare-file scope: `.scitex/<pkg>.yaml` (§5)."""
    (repo / ".scitex/scholar.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(repo, "add", ".scitex/scholar.yaml")
    return repo


@pytest.fixture
def repo_two_breaches(repo: Path) -> Path:
    """One alias plus one gitignored dir, in the same package scope."""
    (repo / ".scitex/dev/dev.yaml").write_text("a: 1\n", encoding="utf-8")
    (repo / ".scitex/dev/cache").mkdir()
    (repo / ".scitex/dev/cache/x").write_text("x", encoding="utf-8")
    (repo / ".gitignore").write_text(".scitex/dev/cache/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", ".scitex/dev/dev.yaml")
    return repo


# --- clean cases -------------------------------------------------------------


def test_ps222_stays_silent_for_canonical_tracked_config_yaml(repo_canonical: Path):
    # Arrange
    target = repo_canonical
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == []


def test_ps222_stays_silent_for_gitignored_runtime_dir(repo_runtime_ignored: Path):
    """CONTROL ARM — a gitignored `runtime/` IS the convention, not a breach.

    If a mutation makes the check flag every entry, THIS test is what catches
    it; every positive test in this file would still pass.
    """
    # Arrange
    target = repo_runtime_ignored
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == []


def test_ps222_stays_silent_when_repo_has_no_scitex_dir(tmp_path: Path):
    # Arrange
    _git(tmp_path, "init", "-q")
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps222_stays_silent_for_untracked_but_unignored_new_file(repo: Path):
    # Arrange — brand-new uncommitted file: untracked, but NOT ignored.
    (repo / ".scitex/dev/config.yaml").write_text("audit: {}\n", encoding="utf-8")
    # Act
    out = _run(repo)
    # Assert — uncommitted work is not a layout violation.
    assert _codes(out) == []


# --- PS-222 fires: deprecated alias -----------------------------------------


def test_ps222_flags_deprecated_pkg_short_yaml_alias(repo_alias: Path):
    # Arrange
    target = repo_alias
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_flags_deprecated_pkg_short_underscore_config_alias(
    repo_alias_underscore: Path,
):
    # Arrange
    target = repo_alias_underscore
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_alias_detail_states_the_canonical_config_yaml_remedy(
    repo_alias_underscore: Path,
):
    # Arrange
    target = repo_alias_underscore
    # Act
    out = _run(target)
    # Assert — the remedy is stated, not merely implied.
    assert "config.yaml" in out[0].detail


def test_ps222_alias_detail_names_the_offending_filename(
    repo_alias_underscore: Path,
):
    # Arrange
    target = repo_alias_underscore
    # Act
    out = _run(target)
    # Assert
    assert "dev_config.yaml" in out[0].detail


# --- PS-222 fires: gitignored non-runtime entry ------------------------------


def test_ps222_flags_gitignored_non_runtime_dir(repo_ignored_dir: Path):
    # Arrange
    target = repo_ignored_dir
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_ignored_dir_detail_names_the_offending_dir(repo_ignored_dir: Path):
    # Arrange
    target = repo_ignored_dir
    # Act
    out = _run(target)
    # Assert
    assert "cache" in out[0].detail


def test_ps222_flags_gitignored_non_runtime_file(repo_ignored_file: Path):
    # Arrange
    target = repo_ignored_file
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_ignored_file_detail_names_the_offending_file(repo_ignored_file: Path):
    # Arrange
    target = repo_ignored_file
    # Act
    out = _run(target)
    # Assert
    assert "secrets.yaml" in out[0].detail


# --- PS-222 fires: bare-file scope -------------------------------------------


def test_ps222_flags_bare_yaml_file_directly_under_scitex_dir(repo_bare_file: Path):
    # Arrange
    target = repo_bare_file
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_bare_file_detail_says_the_scope_must_be_a_directory(
    repo_bare_file: Path,
):
    # Arrange
    target = repo_bare_file
    # Act
    out = _run(target)
    # Assert
    assert "DIRECTORY" in out[0].detail


# --- one finding per offending entry -----------------------------------------


def test_ps222_emits_one_finding_per_offending_entry(repo_two_breaches: Path):
    # Arrange
    target = repo_two_breaches
    # Act
    out = _run(target)
    # Assert
    assert _codes(out) == ["PS-222", "PS-222"]


def test_ps222_findings_point_at_distinct_sites(repo_two_breaches: Path):
    # Arrange
    target = repo_two_breaches
    # Act
    out = _run(target)
    # Assert — two distinct sites, not one merged finding reported twice.
    assert len({v.where for v in out}) == 2


# --- exemptions --------------------------------------------------------------


def test_ps222_accepted_exemption_silences_the_named_site(repo_ignored_dir: Path):
    # Arrange
    cfg = _StubConfig(accepted={("PS-222", ".scitex/dev/cache", 0)})
    # Act
    out = _run(repo_ignored_dir, config=cfg)
    # Assert
    assert _codes(out) == []


def test_ps222_reports_rejected_exemption_entry_as_a_finding(repo_canonical: Path):
    # Arrange — a clean tree, but a REJECTED exemption entry in the config.
    cfg = _StubConfig(errors=("PS-222[0]: missing `reason`",))
    # Act
    out = _run(repo_canonical, config=cfg)
    # Assert
    assert _codes(out) == ["PS-222"]


def test_ps222_rejected_exemption_finding_says_it_exempts_nothing(
    repo_canonical: Path,
):
    # Arrange
    cfg = _StubConfig(errors=("PS-222[0]: missing `reason`",))
    # Act
    out = _run(repo_canonical, config=cfg)
    # Assert — the rejection reads as an error, never as a quiet no-op.
    assert "does NOT exempt anything" in out[0].detail


def test_ps222_rejected_exemption_does_not_silence_the_site(repo_ignored_dir: Path):
    # Arrange — an ignored dir AND a rejected exemption naming it.
    cfg = _StubConfig(errors=("PS-222[0]: missing `reason`",))
    # Act
    out = _run(repo_ignored_dir, config=cfg)
    # Assert — the config error AND the still-live site.
    assert _codes(out) == ["PS-222", "PS-222"]


def test_ps222_rejected_exemption_for_another_rule_is_not_reported(
    repo_canonical: Path,
):
    # Arrange — a rejection notice belonging to PS-220, not PS-222.
    cfg = _StubConfig(errors=("PS-220[0]: missing `reason`",))
    # Act
    out = _run(repo_canonical, config=cfg)
    # Assert
    assert _codes(out) == []


# --- registration ------------------------------------------------------------


def test_ps222_is_registered_at_severity_w():
    # Arrange
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    rule = RULES["PS-222"]
    # Assert — severity ships in the rule tuple (a co-located rule cannot be
    # reached by `_SEVERITY_OVERRIDES`; see `_registry.py` note by `_patch`).
    assert rule.severity == "W"


def test_ps222_is_registered_with_its_slug():
    # Arrange
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    rule = RULES["PS-222"]
    # Assert
    assert rule.slug == "scitex-config-layout"


# EOF
