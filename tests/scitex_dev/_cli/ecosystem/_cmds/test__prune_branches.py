#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev ecosystem prune-branches` — the CLI contract.

No mocks: a REAL git repo under `tmp_path`, driven through
`click.testing.CliRunner`, exactly like the sibling `test__prune_merged`.
The engine's own safety properties are pinned in
`tests/scitex_dev/hygiene/`; these tests pin what the VERB does — that
dry-run is the default, that JSON is parseable, and that the report says
what it protected rather than only what it would delete.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _build_repo(repo: Path) -> None:
    """develop + a merged branch + an unmerged branch + a protected release."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "checkout", "-q", "-b", "develop")
    (repo / "f.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "branch", "main")
    _git(repo, "checkout", "-q", "-b", "feature/merged")
    (repo / "f.txt").write_text("merged\n")
    _git(repo, "commit", "-aqm", "merged change")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "feature/merged")
    _git(repo, "checkout", "-q", "-b", "feature/unmerged")
    (repo / "g.txt").write_text("un\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "unmerged change")
    _git(repo, "checkout", "-q", "-b", "release/1.0", "develop")
    _git(repo, "checkout", "-q", "develop")


def _branches(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"], text=True
    )
    return [b.strip() for b in out.splitlines() if b.strip()]


def _invoke(args, *, repo: Path):
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return CliRunner().invoke(
        main,
        ["ecosystem", "prune-branches", "--repo", str(repo), *args],
        catch_exceptions=False,
    )


@pytest.fixture
def repo(tmp_path):
    target = tmp_path / "pkg"
    _build_repo(target)
    yield target


def test_dry_run_is_the_default_and_deletes_nothing(repo):
    """Required property 5, at the CLI boundary."""
    # Arrange
    before = _branches(repo)
    # Act
    _invoke(["--json"], repo=repo)
    # Assert
    assert _branches(repo) == before


def test_apply_without_config_still_deletes_nothing(repo):
    """Required property 1: --apply alone is not enough. Config gates it."""
    # Arrange
    before = _branches(repo)
    # Act
    _invoke(["--apply", "--json"], repo=repo)
    # Assert
    assert _branches(repo) == before


def test_json_output_parses(repo):
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    # Assert
    assert json.loads(result.output)["apply"] is False


def test_json_reports_the_repo_as_disabled(repo):
    """DEFAULT OFF is visible in the payload, not merely implied by inaction."""
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    payload = json.loads(result.output)
    # Assert
    assert payload["results"][0]["enabled"] is False


def test_json_states_why_the_repo_is_off(repo):
    """OFF is never silent."""
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    payload = json.loads(result.output)
    # Assert
    assert payload["results"][0]["config_error"]


def test_json_reports_the_effective_age_floor(repo):
    """The operator can see the floor without reading source."""
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    payload = json.loads(result.output)
    # Assert
    assert payload["results"][0]["min_age_days"] >= 14.0


def test_json_never_lists_a_protected_branch_as_a_candidate(repo):
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    candidates = json.loads(result.output)["results"][0]["candidates"]
    # Assert
    assert not ({"develop", "main", "release/1.0"} & set(candidates))


def test_json_reports_keep_reasons_for_the_survivors(repo):
    """Required property 7's spirit: never a bare count."""
    # Arrange
    # Act
    result = _invoke(["--json"], repo=repo)
    payload = json.loads(result.output)
    # Assert
    assert payload["results"][0]["keep_reasons"] != {}


def test_text_report_names_what_it_protected(repo):
    """The report must say what it PROTECTED, not only what it would delete."""
    # Arrange
    # Act
    result = _invoke([], repo=repo)
    # Assert
    assert "kept:" in result.output


def test_text_report_states_the_default_off_state(repo):
    # Arrange
    # Act
    result = _invoke([], repo=repo)
    # Assert
    assert "DISABLED (default OFF)" in result.output


def test_help_mentions_that_it_is_default_off():
    """An operator reading --help must learn the gate before running it."""

    # Arrange
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    # Act
    result = CliRunner().invoke(main, ["ecosystem", "prune-branches", "--help"])
    # Assert
    assert "DEFAULT OFF" in result.output


# EOF
