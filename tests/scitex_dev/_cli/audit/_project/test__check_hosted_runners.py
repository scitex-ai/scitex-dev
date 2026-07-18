# -*- coding: utf-8 -*-
"""PS-169 — GitHub-hosted runners are forbidden (operator mandate 2026-07-14).

This rule is the ONLY enforcement that exists (GitHub cannot block hosted
runners below the Enterprise plan), so its coverage is load-bearing. The
matching design constraint is the inverse — it must NOT false-positive on the
scitex self-hosted idiom, which resolves via `fromJSON(vars.CI_RUNS_ON ||
'[...self-hosted...]')`. Both directions are exercised here.

The check runs against `tmp_path` (no `.git`), so the new-vs-baseline
severity ratchet degrades silently and every finding keeps the rule default
(W) — the tests assert on presence/count/code, not on escalated severity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_hosted_runners import (
    check_ps169_hosted_runners,
)


@dataclass
class _Violation:
    """Stand-in for the auditor's Violation record (`rule, where, detail`)."""

    rule: str
    where: str
    detail: str


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
