# -*- coding: utf-8 -*-
"""Tests for `_check_precommit_hooks.py` (PS-HOOK-001).

A `language: system` pre-commit hook resolves its entry from the ambient
`$PATH`. When the entry is a Python tool, that means "run whichever virtualenv
happens to be active at commit time" — a different interpreter, with a different
package set, on every machine.

Each test builds a REAL temp repo (`tmp_path`) with a real
`.pre-commit-config.yaml` and a real `pyproject.toml`. No mocks (NM001-003).

The load-bearing negative test is `test_silent_on_bash_grep_debug_hook`: that
hook's entry *contains the literal strings* `pdb.set_trace` and `breakpoint()`
as grep patterns, but the invoked command is `grep`. A naive substring scan
flags it; only a command-position scan gets it right. It is a real hook, live in
four fleet repos today.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_precommit_hooks import (
    check_ps_hook_001_precommit_system_hooks,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_config(repo: Path, hooks_yaml: str) -> None:
    """Write a `.pre-commit-config.yaml` with a single `repo: local` block."""
    repo.joinpath(".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n" + hooks_yaml,
        encoding="utf-8",
    )


def _write_pyproject(repo: Path, *, dev_extra: str = "") -> None:
    extras = ""
    if dev_extra:
        extras = f"[project.optional-dependencies]\ndev = [{dev_extra}]\n"
    repo.joinpath("pyproject.toml").write_text(
        '[project]\nname = "fakepkg"\ndependencies = ["numpy"]\n' + extras,
        encoding="utf-8",
    )


def _run(repo: Path) -> list:
    out: list = []
    check_ps_hook_001_precommit_system_hooks(repo, _StubViolation, out)
    return out


# --- PS-HOOK-001 fires (positive cases) -------------------------------------


def test_fires_on_system_python_m_pytest_testmon(tmp_path):
    # Arrange — the figrecipe incident shape: ran ZERO tests fleet-wide.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pytest-testmon\n"
        "        name: pytest-testmon\n"
        "        entry: python -m pytest --testmon\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert [v.rule for v in out] == ["PS-HOOK-001"]


def test_fires_on_system_bare_pytest_entry(tmp_path):
    # Arrange — the pyposter shape: a bare `pytest` $PATH lookup.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pytest\n"
        "        name: pytest\n"
        "        entry: pytest tests/ -v --tb=short\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert [v.rule for v in out] == ["PS-HOOK-001"]


def test_fires_on_pytest_wrapped_in_bash_dash_c(tmp_path):
    # Arrange — the pip-project-template shape: the tool hides inside `bash -c`.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: smoke-tests\n"
        "        name: Run smoke tests\n"
        "        entry: bash -c 'pytest tests/ -k \"smoke\" -q --maxfail=1'\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert [v.rule for v in out] == ["PS-HOOK-001"]


def test_fires_on_system_mypy_not_only_pytest(tmp_path):
    # Arrange — the rule is about ambient PYTHON TOOLS, not about pytest alone.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: mypy\n"
        "        name: mypy\n"
        "        entry: mypy src/\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert [v.rule for v in out] == ["PS-HOOK-001"]


def test_detail_names_the_invoked_tool(tmp_path):
    # Arrange
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pytest\n        entry: pytest tests/\n        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "pytest" in out[0].detail


def test_detail_says_undeclared_when_dep_absent(tmp_path):
    # Arrange — the davinci-resolve-mcp shape: pytest is nowhere in the deps.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pytest\n"
        "        entry: python -m pytest tests/\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "not declared in this repo's dependencies" in out[0].detail


def test_detail_rejects_dev_extra_as_insufficient(tmp_path):
    # Arrange — pytest IS in [dev], which does NOT put it on the committer's PATH.
    _write_pyproject(tmp_path, dev_extra='"pytest>=8.0.0"')
    _write_config(
        tmp_path,
        "      - id: pytest\n        entry: pytest tests/\n        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "never activates your dev venv" in out[0].detail


def test_where_field_identifies_the_offending_hook(tmp_path):
    # Arrange
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: smoke-tests\n"
        "        entry: pytest tests/\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out[0].where.endswith(":smoke-tests")


# --- PS-HOOK-001 silent (negative cases) ------------------------------------


def test_silent_on_bash_grep_debug_hook(tmp_path):
    # Arrange — LIVE in four fleet repos. The entry CONTAINS the strings
    # `pdb.set_trace` and `breakpoint()`, but the invoked command is `grep`.
    # A substring scan false-positives here; a command-position scan does not.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: no-debug-code\n"
        "        name: Check for debug code\n"
        '        entry: bash -c \'! grep -rn "import pdb\\|pdb.set_trace\\|breakpoint()" src/'
        ' || (echo "Debug code found!" && false)\'\n'
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_on_non_python_node_toolchain(tmp_path):
    # Arrange — openclaw's pnpm hook: a legitimate `language: system` tool.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pnpm-audit-prod\n"
        "        entry: pnpm audit --prod --audit-level=high\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_on_non_python_swift_toolchain(tmp_path):
    # Arrange — openclaw's swiftlint hook.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: swiftlint\n"
        "        entry: swiftlint --config .swiftlint.yml\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_on_language_python_with_additional_dependencies(tmp_path):
    # Arrange — openclaw's exemplar: THE CORRECT PATTERN. pre-commit builds an
    # isolated venv and installs pytest into it, so nothing is ambient.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: skills-python-tests\n"
        "        entry: pytest -q skills\n"
        "        language: python\n"
        '        additional_dependencies: ["pytest>=8,<9"]\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_on_explicit_repo_local_path(tmp_path):
    # Arrange — an explicit path is a deliberate, repo-controlled choice; it is
    # not a $PATH lookup, so it is not the nondeterminism this rule targets.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: fast-ci\n"
        "        entry: ./scripts/pre-commit/run-tests.sh\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_when_precommit_config_absent(tmp_path):
    # Arrange — a repo with no pre-commit config at all.
    _write_pyproject(tmp_path)
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_silent_when_optout_comment_present(tmp_path):
    # Arrange — the documented escape hatch for a genuinely ambient-safe tool.
    _write_pyproject(tmp_path)
    tmp_path.joinpath(".pre-commit-config.yaml").write_text(
        "# PS-HOOK-001: allow\n"
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: pytest\n"
        "        entry: pytest tests/\n"
        "        language: system\n",
        encoding="utf-8",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_fires_once_per_offending_hook(tmp_path):
    # Arrange — two bad hooks + one legitimate grep hook in the same config.
    _write_pyproject(tmp_path)
    _write_config(
        tmp_path,
        "      - id: pytest\n"
        "        entry: pytest tests/\n"
        "        language: system\n"
        "      - id: mypy\n"
        "        entry: mypy src/\n"
        "        language: system\n"
        "      - id: no-debug-code\n"
        "        entry: bash -c '! grep -rn \"pdb\" src/'\n"
        "        language: system\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert len(out) == 2


# ── audit_project integration (JSON path) ────────────────────────────────


def _build_repo_with_system_pytest_hook(repo: Path) -> None:
    """Arrange helper: a pip package whose pre-commit runs ambient pytest."""
    from scitex_dev._cli.audit._config import write_config

    (repo / ".scitex/dev").mkdir(parents=True)
    write_config(repo, project_types=["pip"])
    _write_pyproject(repo, dev_extra='"pytest>=8.0.0"')
    _write_config(
        repo,
        "      - id: pytest\n"
        "        name: pytest\n"
        "        entry: python -m pytest tests/ -x -q\n"
        "        language: system\n",
    )


def _run_audit_project_json(repo: Path) -> dict:
    """Act helper: run audit_project --json and return the payload."""
    import io
    import json
    from contextlib import redirect_stdout

    from scitex_dev._cli.audit._project._audit import audit_project

    buf = io.StringIO()
    with redirect_stdout(buf):
        audit_project("fakepkg", repo=repo, json_out=True, severity="warning")
    return json.loads(buf.getvalue())


@pytest.fixture
def audit_payload_with_system_pytest_hook(tmp_path):
    """Shared Arrange+Act: audit payload for a repo with the bad hook.

    End-to-end: the rule must survive registration + the engine's
    project-type routing and reach the JSON payload the CI gate reads.
    """
    _build_repo_with_system_pytest_hook(tmp_path)
    return _run_audit_project_json(tmp_path)


def test_audit_project_emits_ps_hook_001(audit_payload_with_system_pytest_hook):
    # Arrange (shared via fixture)
    payload = audit_payload_with_system_pytest_hook
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert
    assert "PS-HOOK-001" in by_rule


def test_audit_project_records_ps_hook_001_severity_e(
    audit_payload_with_system_pytest_hook,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_system_pytest_hook
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert — E means the audit exits non-zero: the gate has teeth.
    assert by_rule["PS-HOOK-001"]["severity"] == "E"


def test_audit_project_ps_hook_001_detail_carries_the_fix(
    audit_payload_with_system_pytest_hook,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_system_pytest_hook
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert — an actionable hint, not just a complaint.
    assert "additional_dependencies" in by_rule["PS-HOOK-001"]["detail"]


# EOF
