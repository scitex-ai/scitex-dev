"""Tests for `_check_workflow_presence.py` (PS-165).

PS-165 (W) — a package is missing one or more of the baseline GitHub
Actions workflows required for its category. A repo with no
`.github/workflows/` at all surfaces a single PS-165; a repo that ships
the full baseline set is clean.

The checker is exercised directly with a stub Violation class.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_workflow_presence import (
    check_ps165_workflow_presence,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# The baseline (library-category) workflow filenames that satisfy every
# _BASELINE_REQUIREMENT pattern. Kept in lockstep with the checker.
_BASELINE_FILES = (
    "cla.yml",
    "pytest-matrix-on-ubuntu-py3-12.yml",
    "import-smoke-on-ubuntu-py3-12.yml",
    "pypi-publish-on-tag.yml",
    # NEUTRAL, not `scitex-dev-quality-audit-*`. The old fixture encoded a
    # pattern that ZERO packages in the fleet satisfied, so this suite was
    # green against a requirement nothing met — the fixture agreed with the
    # checker and both disagreed with reality.
    "quality-audit-on-push.yml",
    "sync-main-to-release-tag-on-push.yml",
)


def _write_workflows(repo: Path, *names: str) -> None:
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    for name in names:
        (wf / name).write_text("name: stub\non: [push]\njobs: {}\n")


class TestPS165WorkflowPresence:
    def test_repo_without_workflows_dir_is_flagged(self, tmp_path: Path) -> None:
        # Arrange — no .github/workflows/ at all
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-165"]

    def test_missing_single_baseline_workflow_is_flagged(
        self, tmp_path: Path
    ) -> None:
        # Arrange — full baseline minus the pytest matrix workflow
        present = tuple(f for f in _BASELINE_FILES if not f.startswith("pytest-"))
        _write_workflows(tmp_path, *present)
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert — exactly one PS-165 for the missing pytest matrix workflow
        assert [v.rule for v in out] == ["PS-165"]

    def test_missing_pytest_workflow_names_pytest_in_detail(
        self, tmp_path: Path
    ) -> None:
        # Arrange — full baseline minus the pytest matrix workflow
        present = tuple(f for f in _BASELINE_FILES if not f.startswith("pytest-"))
        _write_workflows(tmp_path, *present)
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert — the finding identifies the missing pytest matrix workflow
        assert "pytest" in out[0].detail

    def test_full_baseline_set_produces_no_finding(self, tmp_path: Path) -> None:
        # Arrange — control arm: every baseline workflow present
        _write_workflows(tmp_path, *_BASELINE_FILES)
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert
        assert out == []


_TAG_FLOW_PUBLISH = (
    "name: release\n"
    "on:\n"
    "  push:\n"
    "    tags: ['v*']\n"
    "jobs:\n"
    "  publish:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps: []\n"
)

_BRANCH_FLOW_PUBLISH = (
    "name: release\non:\n  push:\n    branches: [main]\njobs: {}\n"
)


def _write_publish_workflow(repo: Path, body: str) -> None:
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "pypi-publish-on-tag.yml").write_text(body)


def _baseline_without(repo: Path, *missing_fragments: str) -> None:
    present = tuple(
        f
        for f in _BASELINE_FILES
        if not any(frag in f for frag in missing_fragments)
    )
    _write_workflows(repo, *present)


class TestPS165TagFlowWaiver:
    def test_tag_flow_repo_waives_sync_main_only(self, tmp_path: Path) -> None:
        # Arrange — full baseline minus sync-main and minus the stub
        # publisher, plus a tag-triggered publisher: releases are cut by
        # tagging, so there is no main→release-tag sync to perform.
        _baseline_without(tmp_path, "sync-main", "pypi-")
        _write_publish_workflow(tmp_path, _TAG_FLOW_PUBLISH)
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert
        assert out == []

    def test_branch_flow_repo_still_requires_sync_main(
        self, tmp_path: Path
    ) -> None:
        # Arrange — negative control: the publisher triggers on branches,
        # not tags, so the waiver does not apply.
        _baseline_without(tmp_path, "sync-main", "pypi-")
        _write_publish_workflow(tmp_path, _BRANCH_FLOW_PUBLISH)
        out: list = []
        # Act
        check_ps165_workflow_presence(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-165"]
