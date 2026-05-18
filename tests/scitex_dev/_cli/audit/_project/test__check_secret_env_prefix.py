"""Tests for `_check_secret_env_prefix.py` (PS-168).

Per-project secrets in `.github/workflows/*.yml` must carry the
package's `<PKG>_` prefix. Cross-cutting names (rotate-all target,
tool-pinned tokens) are exempted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_secret_env_prefix import (
    EXCEPTION_SECRETS,
    _distribution_prefix,
    _violations_in_text,
    check_ps168_secret_env_prefix,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== fixtures =====


_CLEAN_WORKFLOW = """\
name: pytest
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Use prefixed secret
        env:
          CLAUDE_CODE_CREDENTIALS_JSON: ${{ secrets.NEWB_CLAUDE_CODE_CREDENTIALS_JSON }}
        run: echo "ok"
      - name: Use cross-cutting exception
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
        run: echo "still ok"
"""


_VIOLATING_WORKFLOW = """\
name: tests
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Wrong — un-prefixed per-package secret
        env:
          CLAUDE_CREDENTIALS_JSON: ${{ secrets.CLAUDE_CREDENTIALS_JSON }}
        run: echo "broken"
      - name: Wrong — un-prefixed custom secret
        env:
          MY_API_KEY: ${{ secrets.MY_API_KEY }}
        run: echo "also broken"
"""


_MIXED_WORKFLOW = """\
name: deploy
on:
  push:
    tags: ["v*"]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.NEWB_DEPLOY_KEY }}"
      - run: echo "${{ secrets.GITHUB_TOKEN }}"
      - run: echo "${{ secrets.OPENAI_KEY }}"
"""


def _write_workflow(repo: Path, filename: str, body: str) -> None:
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / filename).write_text(body, encoding="utf-8")


# ===== _distribution_prefix =====


class TestDistributionPrefix:
    def test_simple_lowercase_name_becomes_uppercase_underscore_suffix(
        self,
    ) -> None:
        # Arrange
        distribution = "newb"
        # Act
        result = _distribution_prefix(distribution)
        # Assert
        assert result == "NEWB_"

    def test_hyphenated_name_converts_hyphens_to_underscores(self) -> None:
        # Arrange
        distribution = "scitex-agent-container"
        # Act
        result = _distribution_prefix(distribution)
        # Assert
        assert result == "SCITEX_AGENT_CONTAINER_"

    def test_already_uppercase_name_is_preserved(self) -> None:
        # Arrange
        distribution = "SCITEX-DEV"
        # Act
        result = _distribution_prefix(distribution)
        # Assert
        assert result == "SCITEX_DEV_"


# ===== _violations_in_text =====


class TestViolationsInText:
    def test_clean_workflow_returns_no_violations(self) -> None:
        # Arrange
        text = _CLEAN_WORKFLOW
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert result == []

    def test_violating_workflow_returns_two_findings(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert len(result) == 2

    def test_violating_workflow_names_include_first_offender(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert "CLAUDE_CREDENTIALS_JSON" in {name for _, name in result}

    def test_violating_workflow_names_include_second_offender(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert "MY_API_KEY" in {name for _, name in result}

    def test_mixed_workflow_flags_only_unprefixed_non_exception_name(
        self,
    ) -> None:
        # Arrange
        text = _MIXED_WORKFLOW
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert [name for _, name in result] == ["OPENAI_KEY"]

    def test_every_exception_secret_is_never_flagged(self) -> None:
        # Arrange — every exception name embedded as a secret ref
        body_lines = [f"echo '${{{{ secrets.{name} }}}}'" for name in EXCEPTION_SECRETS]
        text = "\n".join(body_lines) + "\n"
        # Act
        result = _violations_in_text(text, prefix="UNRELATED_PKG_")
        # Assert
        assert result == []

    def test_line_number_is_one_based_on_third_line(self) -> None:
        # Arrange
        text = "line one\nline two\n${{ secrets.UNPREFIXED }}\n"
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert result == [(3, "UNPREFIXED")]

    def test_whitespace_inside_interpolation_braces_is_tolerated(self) -> None:
        # Arrange
        text = "${{   secrets  .  FOO_BAR  }}\n"
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert result == [(1, "FOO_BAR")]

    def test_correctly_prefixed_secret_is_never_flagged(self) -> None:
        # Arrange
        text = "env:\n  X: ${{ secrets.NEWB_SOMETHING }}\n"
        # Act
        result = _violations_in_text(text, prefix="NEWB_")
        # Assert
        assert result == []


# ===== check_ps168_secret_env_prefix (integration) =====


class TestCheckPS168Integration:
    def test_clean_repo_emits_no_violations(self, tmp_path: Path) -> None:
        # Arrange
        _write_workflow(tmp_path, "pytest-on-ubuntu.yml", _CLEAN_WORKFLOW)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out == []

    def test_violating_repo_emits_two_violation_entries(self, tmp_path: Path) -> None:
        # Arrange
        _write_workflow(tmp_path, "tests.yml", _VIOLATING_WORKFLOW)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert len(out) == 2

    def test_violating_repo_tags_each_violation_with_ps168(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _write_workflow(tmp_path, "tests.yml", _VIOLATING_WORKFLOW)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert all(v.rule == "PS-168" for v in out)

    def test_violating_repo_records_workflow_path_with_line_suffix(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _write_workflow(tmp_path, "tests.yml", _VIOLATING_WORKFLOW)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert all(v.where.startswith(".github/workflows/tests.yml:") for v in out)

    def test_empty_repo_without_workflows_dir_passes_silently(
        self, tmp_path: Path
    ) -> None:
        # Arrange — empty repo, no .github/
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out == []

    def test_hyphenated_distribution_accepts_underscore_prefixed_secrets(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        body = (
            "name: t\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ${{ secrets.SCITEX_AGENT_CONTAINER_NAS_KEY }}\n"
            "      - run: echo ${{ secrets.OTHER_UNPREFIXED }}\n"
        )
        _write_workflow(tmp_path, "ci-on-ubuntu.yml", body)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(
            tmp_path, "scitex-agent-container", _StubViolation, out
        )
        # Assert
        assert len(out) == 1

    def test_hyphenated_distribution_error_message_suggests_canonical_prefix(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        body = (
            "name: t\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ${{ secrets.OTHER_UNPREFIXED }}\n"
        )
        _write_workflow(tmp_path, "ci-on-ubuntu.yml", body)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(
            tmp_path, "scitex-agent-container", _StubViolation, out
        )
        # Assert
        assert "SCITEX_AGENT_CONTAINER_OTHER_UNPREFIXED" in out[0].detail

    def test_single_violation_records_exact_line_number_in_where(
        self, tmp_path: Path
    ) -> None:
        # Arrange — secret ref deliberately on line 7
        body = (
            "name: t\n"
            "on: [push]\n"
            "jobs:\n"
            "  j:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: ${{ secrets.UNPREFIXED }}\n"
        )
        _write_workflow(tmp_path, "x-on-ubuntu.yml", body)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out[0].where == ".github/workflows/x-on-ubuntu.yml:7"
