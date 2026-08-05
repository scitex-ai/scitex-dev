# -*- coding: utf-8 -*-
"""PS-169 — GitHub-hosted runners are ADVISORY (W); hosted is permitted.

The rule REPORTS that a job runs on a hosted runner (slower than hardware we
own) and never blocks. Detection is still load-bearing — the fleet's migration
inventory reads these findings — so both directions are exercised: a hosted
runner must be found, and the scitex self-hosted idiom
(`fromJSON(vars.CI_RUNS_ON || '[...self-hosted...]')`) must NOT false-positive.

Most tests run against `tmp_path` (no `.git`). The severity contract itself is
pinned separately by `test_new_hosted_runner_is_not_escalated_to_error`, which
uses a REAL git repo — without that, "no escalation" would pass for the
uninteresting reason that no baseline resolves.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_hosted_runners import (
    check_ps169_hosted_runners,
)


@dataclass
class _Violation:
    """Stand-in for the auditor's Violation record (`rule, where, detail`).

    Carries `severity_override` because that is the field the (now removed)
    baseline ratchet used to set to "E". A test cannot observe the ratchet's
    ABSENCE unless the field it would have written exists here.
    """

    rule: str
    where: str
    detail: str
    severity_override: str | None = field(default=None)


def _run_rule_on(repo: Path) -> list[_Violation]:
    """Run PS-169 against a repo root and return its violations."""
    out: list[_Violation] = []
    check_ps169_hosted_runners(repo, _Violation, out)
    return out


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty repo skeleton with a `.github/workflows/` directory."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


def _write_workflow(repo: Path, name: str, body: str) -> None:
    (repo / ".github" / "workflows" / name).write_text(body, encoding="utf-8")


# --- (a) literal hosted runner is flagged ------------------------------------


def test_direct_literal_hosted_runner_is_reported(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


def test_direct_literal_hosted_runner_is_tagged_ps169(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found[0].rule == "PS-169"


def test_hosted_runner_in_list_form_is_reported(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "listform.yml",
        "name: l\non: [push]\njobs:\n  b:\n    runs-on: [ubuntu-22.04]\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


# --- (b) the scitex fromJSON self-hosted idiom is NOT flagged ----------------


def test_scitex_fromjson_self_hosted_idiom_is_not_reported(repo: Path) -> None:
    # Arrange — the canonical fleet idiom: fromJSON default resolves to a
    # self-hosted label set, so it must NOT be flagged.
    _write_workflow(
        repo,
        "idiom.yml",
        "name: i\non: [push]\njobs:\n  t:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || "
        "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


def test_fromjson_idiom_with_hosted_default_is_reported(repo: Path) -> None:
    # Arrange — the same idiom SHAPE but with a HOSTED default is a real
    # violation (proves it's the resolved labels being judged, not the syntax).
    _write_workflow(
        repo,
        "idiom-bad.yml",
        "name: i\non: [push]\njobs:\n  t:\n"
        "    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '[\"ubuntu-latest\"]') }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


# --- (c) plain self-hosted list is NOT flagged -------------------------------


def test_plain_self_hosted_runner_list_is_not_reported(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "clean.yml",
        "name: c\non: [push]\njobs:\n  t:\n"
        "    runs-on: [self-hosted, Linux, X64, scitex-ci]\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


# --- (d) a matrix over hosted labels is flagged ------------------------------


def test_hosted_runner_reached_via_matrix_expression_is_reported(repo: Path) -> None:
    # Arrange — the case a literal `runs-on:` grep cannot see: the line says
    # `${{ matrix.os }}`, and the hosted images hide in strategy.matrix.
    _write_workflow(
        repo,
        "matrix.yml",
        "name: m\non: [push]\njobs:\n  tests:\n"
        "    strategy:\n      matrix:\n        os: [ubuntu-latest, macos-14]\n"
        "    runs-on: ${{ matrix.os }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert — one per resolved hosted image.
    assert [v.rule for v in found] == ["PS-169", "PS-169"]


def test_matrix_over_self_hosted_labels_is_not_reported(repo: Path) -> None:
    # Arrange — a matrix whose values are all self-hosted must stay clean.
    _write_workflow(
        repo,
        "matrix-clean.yml",
        "name: m\non: [push]\njobs:\n  t:\n"
        "    strategy:\n      matrix:\n        runner: [scitex-ci, spartan-cpu]\n"
        "    runs-on: ${{ matrix.runner }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


# --- (e) a repo with no workflows is clean (not an error) --------------------


def test_repo_without_workflows_directory_is_not_reported(tmp_path: Path) -> None:
    # Arrange — no .github/workflows/ at all.
    # Act
    found = _run_rule_on(tmp_path)
    # Assert
    assert found == []


def test_empty_workflows_directory_is_not_reported(repo: Path) -> None:
    # Arrange — directory present but empty.
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


# --- no-false-positive: an unresolvable runner is NOT flagged ----------------


def test_unresolvable_runner_expression_is_not_reported(repo: Path) -> None:
    # Arrange — an expression we cannot statically resolve (a bare vars ref
    # with no in-workflow default) is left to the human, never guessed as a
    # violation. This is the deliberate no-false-positive design vs. PR #344.
    _write_workflow(
        repo,
        "unknown.yml",
        "name: u\non: [push]\njobs:\n  t:\n    runs-on: ${{ vars.RUNNER }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


def test_workflow_call_input_default_hosted_is_reported(repo: Path) -> None:
    # Arrange — inputs.<key> resolves to its workflow_call default.
    _write_workflow(
        repo,
        "called.yml",
        "name: c\non:\n  workflow_call:\n    inputs:\n      runner:\n"
        "        type: string\n        default: ubuntu-latest\n"
        "jobs:\n  tests:\n    runs-on: ${{ inputs.runner }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


# --- fallback: a hosted literal in unparseable YAML is still caught ----------


def test_hosted_runner_in_unparseable_yaml_is_still_reported(repo: Path) -> None:
    # Arrange — a broken file must not smuggle an outright hosted literal past.
    _write_workflow(
        repo,
        "broken.yml",
        "name: b\non: [push\njobs:\n  t:\n    runs-on: ubuntu-latest\n  : : :\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


# --- messages carry the rule code + a self-hosted remedy ---------------------


def test_violation_names_the_self_hosted_remedy(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert "scitex-ci" in found[0].detail


@pytest.fixture
def repo_on_hosted_runner(repo: Path) -> Path:
    """A repo whose single job runs on a plain GitHub-hosted runner."""
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    return repo


def test_violation_says_hosted_is_allowed(repo_on_hosted_runner: Path) -> None:
    # Arrange
    target = repo_on_hosted_runner
    # Act
    detail = _run_rule_on(target)[0].detail
    # Assert
    assert "ALLOWED" in detail


def test_violation_no_longer_calls_hosted_forbidden(
    repo_on_hosted_runner: Path,
) -> None:
    """A rule reporting at W while its text says "forbidden without exception"
    teaches the reader the opposite of what the gate does — and that text is
    what agents act on."""
    # Arrange
    target = repo_on_hosted_runner
    # Act
    detail = _run_rule_on(target)[0].detail
    # Assert
    assert "forbidden" not in detail.lower()


# --- the ratchet is GONE (real git repo, or the test proves nothing) ---------


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def newly_hosted_git_repo(tmp_path: Path) -> Path:
    """A job MOVED onto a hosted runner atop a clean `develop` baseline.

    This is the shape of a PR complying with the 2026-08-05 directive: a repo
    whose CI ran on our own hardware moves a job to a hosted runner. The
    removed ratchet escalated exactly this to E — blocking the compliant
    change while leaving every long-standing `ubuntu-latest` at W, i.e.
    permitting the status quo and forbidding its correction. Measured on
    scitex-hub's PR #561.

    The repo MUST be a REAL git repo with a resolvable `develop` baseline. On
    a bare `tmp_path` the ratchet degrades to "no escalation" by itself, so
    these assertions would pass against the unfixed code and prove nothing.
    """
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "test")
    _write_workflow(
        repo,
        "ci.yml",
        "name: ci\non: [push]\njobs:\n"
        "  tests:\n    runs-on: [self-hosted, Linux, X64, scitex-ci]\n",
    )
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "seed")
    _run_git(repo, "branch", "-M", "develop")

    # The change under review.
    _write_workflow(
        repo,
        "ci.yml",
        "name: ci\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    return repo


def test_new_hosted_runner_is_still_reported(newly_hosted_git_repo: Path) -> None:
    # Arrange
    target = newly_hosted_git_repo
    # Act
    found = _run_rule_on(target)
    # Assert — detection is unchanged; only the consequence moved.
    assert len(found) == 1


def test_new_hosted_runner_is_not_escalated_to_error(
    newly_hosted_git_repo: Path,
) -> None:
    # Arrange
    target = newly_hosted_git_repo
    # Act
    found = _run_rule_on(target)
    # Assert — this is the assertion the fix exists for.
    assert found[0].severity_override is None
