"""PS-169 — GitHub-hosted runners are forbidden (operator mandate 2026-07-14).

The rule is the ONLY enforcement that exists (GitHub cannot block hosted
runners below the Enterprise plan), so its coverage is load-bearing: every
form the runner can take is exercised here, including the indirect ones a
naive `grep ubuntu-latest` would miss.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_hosted_runners import (
    check_ps169_hosted_runners,
)


class _Violation:
    """Stand-in for the auditor's Violation record (real class, not a mock)."""

    def __init__(self, code: str, where: str, message: str) -> None:
        self.code = code
        self.where = where
        self.message = message


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


def test_direct_hosted_runner_is_reported(repo: Path) -> None:
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


def test_hosted_runner_reached_via_matrix_expression_is_reported(repo: Path) -> None:
    # Arrange — the case a literal `runs-on:` grep cannot see: the line says
    # `${{ matrix.os }}`, and the hosted image hides in strategy.matrix.
    _write_workflow(
        repo,
        "matrix.yml",
        "name: m\non: [push]\njobs:\n  tests:\n"
        "    strategy:\n      matrix:\n        os: [ubuntu-latest, macos-14]\n"
        "    runs-on: ${{ matrix.os }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 2


def test_hosted_runner_from_workflow_call_input_default_is_reported(repo: Path) -> None:
    # Arrange
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


def test_unresolvable_runner_expression_is_reported(repo: Path) -> None:
    # Arrange — an unverifiable runner cannot be proven Spartan-only, so it is
    # a violation rather than an assumed pass.
    _write_workflow(
        repo,
        "unknown.yml",
        "name: u\non: [push]\njobs:\n  t:\n    runs-on: ${{ vars.RUNNER }}\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


def test_spartan_self_hosted_runner_is_not_reported(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "clean.yml",
        "name: c\non: [push]\njobs:\n  t:\n"
        "    runs-on: [self-hosted, Linux, X64, spartan-cpu]\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


def test_caller_of_trusted_scitex_reusable_workflow_is_not_reported(repo: Path) -> None:
    # Arrange — the callee's own runs-on is audited by this rule in
    # scitex-ai/.github, so the caller inherits a verified runner.
    _write_workflow(
        repo,
        "caller.yml",
        "name: c\non: [push]\njobs:\n  call:\n"
        "    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found == []


def test_caller_of_untrusted_reusable_workflow_is_reported(repo: Path) -> None:
    # Arrange — a third party's effective runner cannot be vouched for.
    _write_workflow(
        repo,
        "untrusted.yml",
        "name: u\non: [push]\njobs:\n  call:\n"
        "    uses: some-vendor/ci/.github/workflows/build.yml@v1\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


def test_hosted_runner_in_unparseable_yaml_is_still_reported(repo: Path) -> None:
    # Arrange — a broken file must not smuggle a hosted runner past the gate.
    _write_workflow(
        repo,
        "broken.yml",
        "name: b\non: [push\njobs:\n  t:\n    runs-on: ubuntu-latest\n  : : :\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert len(found) == 1


def test_repo_without_workflows_directory_is_not_reported(tmp_path: Path) -> None:
    # Arrange — no .github/workflows/ at all.
    # Act
    found = _run_rule_on(tmp_path)
    # Assert
    assert found == []


def test_violation_message_names_the_spartan_remedy(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert "spartan-cpu" in found[0].message


def test_violation_is_tagged_with_the_ps169_code(repo: Path) -> None:
    # Arrange
    _write_workflow(
        repo,
        "direct.yml",
        "name: d\non: [push]\njobs:\n  tests:\n    runs-on: ubuntu-latest\n",
    )
    # Act
    found = _run_rule_on(repo)
    # Assert
    assert found[0].code == "PS-169"
