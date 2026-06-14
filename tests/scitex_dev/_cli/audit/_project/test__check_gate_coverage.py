"""Tests for PS-185 — gate-covers-CI drift detection.

Card: ``gate-covers-ci-lightweight``. Invariant: every lightweight CI
job declared in ``.github/workflows/*.yml`` must have a corresponding
step in the canonical pre-push gate script. Heavy items (pytest-matrix,
sphinx, codecov) are exempt by design.

No mocks (NM001-003) — real temp dirs + ``tmp_path``. Single assert per
test (PA-307 §3 STX-TQ007 — one observable per test).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_gate_coverage import (
    check_ps185_gate_coverage,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== helpers =====


# A minimal but realistic gate script: contains the substrings the
# default LIGHTWEIGHT_KEYWORDS map looks for (ruff, audit-all,
# import-smoke). Used by the "covered" tests.
_GATE_COVERS_ALL = """\
#!/usr/bin/env bash
# stub pre-push gate for tests.
# [1/4] ecosystem audit-all <pkg>
# [2/4] ruff check --select F401,F811
# [3/4] import-smoke (importlib.import_module)
# [4/4] pytest --testmon
"""

# Gate with NO ruff coverage — used by the "fires" test.
_GATE_MISSING_RUFF = """\
#!/usr/bin/env bash
# [1/4] ecosystem audit-all <pkg>
# [3/4] import-smoke (importlib.import_module)
# [4/4] pytest --testmon
"""


def _make_repo(
    tmp_path: Path,
    workflows: dict[str, str],
    gate_text: str | None = _GATE_COVERS_ALL,
) -> Path:
    """Create a repo skeleton with the given workflow YAML map.

    ``workflows`` maps basename (e.g. ``"tests.yml"``) → YAML body.
    ``gate_text=None`` writes no gate (the rule degrades to silent).
    """
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    for name, body in workflows.items():
        (wf_dir / name).write_text(body)
    if gate_text is not None:
        gate_dir = tmp_path / "src" / "scitex_dev" / "_hooks"
        gate_dir.mkdir(parents=True)
        (gate_dir / "pre-push.sh").write_text(gate_text)
    return tmp_path


def _findings(repo: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_ps185_gate_coverage(repo, _StubViolation, out)
    return [v for v in out if v.rule == "PS-185"]


# ===== rule is SILENT when gate covers all lightweight CI =====


class TestPS185Clean:
    """When every lightweight workflow is mirrored by the gate, no findings."""

    def test_clean_when_gate_covers_ruff_audit_import_smoke(
        self, tmp_path: Path
    ) -> None:
        # Arrange — a "clean" CI surface with three lightweight jobs,
        # all of which the gate covers (the default _GATE_COVERS_ALL).
        repo = _make_repo(
            tmp_path,
            {
                "import-smoke-on-ubuntu.yml": "name: import-smoke\njobs:\n  x:\n    name: import-smoke-on-ubuntu\n",
                "scitex-dev-quality-audit.yml": "name: quality\n",
            },
        )
        # Act
        out = _findings(repo)
        # Assert — no PS-185 findings.
        assert out == [], f"expected zero PS-185 findings, got: {out}"

    def test_clean_when_only_heavy_workflows_present(self, tmp_path: Path) -> None:
        # Arrange — pytest-matrix, sphinx, codecov are all heavy-exempt.
        repo = _make_repo(
            tmp_path,
            {
                "pytest-matrix-on-ubuntu.yml": "name: tests\n",
                "rtd-sphinx-build-on-ubuntu.yml": "name: docs\n",
                "codecov-upload.yml": "name: codecov\n",
            },
        )
        # Act
        out = _findings(repo)
        # Assert — heavy items are exempt; zero findings.
        assert out == [], f"heavy workflows must be exempt, got: {out}"


# ===== rule FIRES when CI has a lightweight job the gate is missing =====


class TestPS185Fires:
    """When CI declares a lightweight job the gate doesn't mirror, flag it."""

    def test_fires_when_new_lint_workflow_added_without_gate_step(
        self, tmp_path: Path
    ) -> None:
        # Arrange — a brand-new `lint.yml` runs `ruff` in CI, but the
        # local gate (intentionally) has NO ruff step. The drift is
        # exactly what PS-185 should catch BEFORE the operator hits red.
        repo = _make_repo(
            tmp_path,
            {
                "lint-on-ubuntu.yml": "name: ruff\njobs:\n  lint:\n    name: ruff-lint-on-ubuntu\n",
            },
            gate_text=_GATE_MISSING_RUFF,
        )
        # Act
        out = _findings(repo)
        # Assert — at least one PS-185 finding citing ruff.
        emitted = (
            len(out) >= 1,
            any("ruff" in v.detail.lower() for v in out),
        )
        assert emitted == (True, True), (
            f"PS-185 must flag missing ruff coverage; got {emitted}\nfindings={out}"
        )

    def test_silenced_by_per_file_exempt_marker(self, tmp_path: Path) -> None:
        # Arrange — same setup as the "fires" test, but the workflow
        # carries the per-file opt-out marker. The rule must respect it.
        repo = _make_repo(
            tmp_path,
            {
                "lint-on-ubuntu.yml": (
                    "# PS-185-exempt: experimental; gate coverage pending\n"
                    "name: ruff\njobs:\n  lint:\n    name: ruff-lint-on-ubuntu\n"
                ),
            },
            gate_text=_GATE_MISSING_RUFF,
        )
        # Act
        out = _findings(repo)
        # Assert — per-file opt-out silences the rule.
        assert out == [], f"PS-185-exempt marker must silence the rule, got: {out}"
