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
    EXCEPTION_SECRETS_DEFAULT,
    _distribution_prefix,
    _exception_secrets_for,
    _read_pyproject_extra_exceptions,
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
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert result == []

    def test_violating_workflow_returns_two_findings(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert len(result) == 2

    def test_violating_workflow_names_include_first_offender(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert "CLAUDE_CREDENTIALS_JSON" in {name for _, name in result}

    def test_violating_workflow_names_include_second_offender(self) -> None:
        # Arrange
        text = _VIOLATING_WORKFLOW
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert "MY_API_KEY" in {name for _, name in result}

    def test_mixed_workflow_flags_only_unprefixed_non_exception_name(
        self,
    ) -> None:
        # Arrange
        text = _MIXED_WORKFLOW
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert [name for _, name in result] == ["OPENAI_KEY"]

    def test_every_exception_secret_is_never_flagged(self) -> None:
        # Arrange — every exception name embedded as a secret ref
        body_lines = [f"echo '${{{{ secrets.{name} }}}}'" for name in EXCEPTION_SECRETS]
        text = "\n".join(body_lines) + "\n"
        # Act
        result = _violations_in_text(text, prefixes="UNRELATED_PKG_")
        # Assert
        assert result == []

    def test_line_number_is_one_based_on_third_line(self) -> None:
        # Arrange — name must be key-like (TOKEN suffix) to be in scope.
        text = "line one\nline two\n${{ secrets.UNPREFIXED_TOKEN }}\n"
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert result == [(3, "UNPREFIXED_TOKEN")]

    def test_whitespace_inside_interpolation_braces_is_tolerated(self) -> None:
        # Arrange — name must be key-like (KEY suffix) to be in scope.
        text = "${{   secrets  .  FOO_API_KEY  }}\n"
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
        # Assert
        assert result == [(1, "FOO_API_KEY")]

    def test_correctly_prefixed_secret_is_never_flagged(self) -> None:
        # Arrange
        text = "env:\n  X: ${{ secrets.NEWB_SOMETHING }}\n"
        # Act
        result = _violations_in_text(text, prefixes="NEWB_")
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
            "      - run: echo ${{ secrets.OTHER_UNPREFIXED_TOKEN }}\n"
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
            "      - run: echo ${{ secrets.OTHER_UNPREFIXED_TOKEN }}\n"
        )
        _write_workflow(tmp_path, "ci-on-ubuntu.yml", body)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(
            tmp_path, "scitex-agent-container", _StubViolation, out
        )
        # Assert
        assert "SCITEX_AGENT_CONTAINER_OTHER_UNPREFIXED_TOKEN" in out[0].detail

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
            "      - run: ${{ secrets.UNPREFIXED_TOKEN }}\n"
        )
        _write_workflow(tmp_path, "x-on-ubuntu.yml", body)
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out[0].where == ".github/workflows/x-on-ubuntu.yml:7"


# ===== per-package exception config (PS-168 pyproject extras) =====


# A secret name that is key-like (TOKEN suffix), NOT in the ecosystem
# default, and NOT prefixed for the `newb` distribution. Without a
# per-package extra it is a PS-168 violation; declaring it as an extra
# exception suppresses the violation.
_LEGACY_SECRET_WORKFLOW = """\
name: legacy-deploy
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.LEGACY_DEPLOY_TOKEN }}"
"""


def _write_pyproject(repo: Path, body: str) -> None:
    (repo / "pyproject.toml").write_text(body, encoding="utf-8")


def _pyproject_with_extras(*names: str) -> str:
    entries = ",\n    ".join(f'"{n}"' for n in names)
    return (
        "[project]\n"
        'name = "newb"\n'
        "[tool.scitex_dev.audit]\n"
        f"ps168_secret_exceptions = [\n    {entries},\n]\n"
    )


class TestReadPyprojectExtraExceptions:
    def test_missing_pyproject_returns_empty_set(self, tmp_path: Path) -> None:
        # Arrange — bare repo, no pyproject.toml
        repo = tmp_path
        # Act
        result = _read_pyproject_extra_exceptions(repo)
        # Assert
        assert result == frozenset()

    def test_pyproject_without_audit_section_returns_empty_set(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _write_pyproject(tmp_path, '[project]\nname = "newb"\n')
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset()

    def test_declared_extras_are_read_as_frozenset(self, tmp_path: Path) -> None:
        # Arrange
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset({"LEGACY_DEPLOY_TOKEN"})

    def test_hyphenated_tool_namespace_is_also_accepted(self, tmp_path: Path) -> None:
        # Arrange — [tool.scitex-dev.audit] (hyphenated spelling)
        body = (
            '[project]\nname = "newb"\n'
            "[tool.scitex-dev.audit]\n"
            'ps168_secret_exceptions = ["LEGACY_DEPLOY_TOKEN"]\n'
        )
        _write_pyproject(tmp_path, body)
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset({"LEGACY_DEPLOY_TOKEN"})

    def test_non_string_entries_are_dropped(self, tmp_path: Path) -> None:
        # Arrange — a mixed list with an int that must be ignored
        body = (
            '[project]\nname = "newb"\n'
            "[tool.scitex_dev.audit]\n"
            'ps168_secret_exceptions = ["GOOD_TOKEN", 42]\n'
        )
        _write_pyproject(tmp_path, body)
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset({"GOOD_TOKEN"})

    def test_wrong_type_for_extras_returns_empty_set(self, tmp_path: Path) -> None:
        # Arrange — ps168_secret_exceptions is a string, not a list
        body = (
            '[project]\nname = "newb"\n'
            "[tool.scitex_dev.audit]\n"
            'ps168_secret_exceptions = "NOT_A_LIST"\n'
        )
        _write_pyproject(tmp_path, body)
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset()

    def test_malformed_toml_returns_empty_set(self, tmp_path: Path) -> None:
        # Arrange — invalid TOML must not raise, just yield no extras
        _write_pyproject(tmp_path, "this is = = not valid toml [[[\n")
        # Act
        result = _read_pyproject_extra_exceptions(tmp_path)
        # Assert
        assert result == frozenset()


class TestExceptionSecretsFor:
    def test_no_pyproject_falls_back_to_ecosystem_default(self, tmp_path: Path) -> None:
        # Arrange — repo without pyproject declares no extras
        repo = tmp_path
        # Act
        result = _exception_secrets_for(repo)
        # Assert
        assert result == EXCEPTION_SECRETS_DEFAULT

    def test_declared_extras_extend_the_default(self, tmp_path: Path) -> None:
        # Arrange
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        # Act
        result = _exception_secrets_for(tmp_path)
        # Assert
        assert result == EXCEPTION_SECRETS_DEFAULT | {"LEGACY_DEPLOY_TOKEN"}

    def test_default_members_are_never_lost_when_extras_declared(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        # Act
        result = _exception_secrets_for(tmp_path)
        # Assert
        assert "CLAUDE_CODE_CREDENTIALS_JSON" in result


class TestCheckPS168PerPackageExceptions:
    def test_undeclared_legacy_secret_is_flagged_as_violation(
        self, tmp_path: Path
    ) -> None:
        # Arrange — workflow uses a non-default, un-prefixed secret; no extras
        _write_workflow(tmp_path, "legacy-on-ubuntu.yml", _LEGACY_SECRET_WORKFLOW)
        _write_pyproject(tmp_path, '[project]\nname = "newb"\n')
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert len(out) == 1

    def test_declared_extra_secret_suppresses_the_violation(
        self, tmp_path: Path
    ) -> None:
        # Arrange — same workflow, but the secret is declared as an extra
        _write_workflow(tmp_path, "legacy-on-ubuntu.yml", _LEGACY_SECRET_WORKFLOW)
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out == []

    def test_default_exception_still_passes_when_extras_declared(
        self, tmp_path: Path
    ) -> None:
        # Arrange — workflow uses an ecosystem-default secret; pkg declares
        # an unrelated extra. The default must still be honoured.
        body = (
            "name: t\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ${{ secrets.GH_TOKEN }}\n"
        )
        _write_workflow(tmp_path, "ci-on-ubuntu.yml", body)
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert
        assert out == []

    def test_declared_extra_does_not_excuse_other_unprefixed_secret(
        self, tmp_path: Path
    ) -> None:
        # Arrange — declaring one extra must not widen the allow-list to a
        # different un-prefixed secret in the same workflow.
        body = (
            "name: t\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo ${{ secrets.LEGACY_DEPLOY_TOKEN }}\n"
            "      - run: echo ${{ secrets.OTHER_RANDOM_TOKEN }}\n"
        )
        _write_workflow(tmp_path, "ci-on-ubuntu.yml", body)
        _write_pyproject(tmp_path, _pyproject_with_extras("LEGACY_DEPLOY_TOKEN"))
        out: list = []
        # Act
        check_ps168_secret_env_prefix(tmp_path, "newb", _StubViolation, out)
        # Assert — exactly the un-declared secret remains flagged
        assert [("OTHER_RANDOM_TOKEN" in v.detail) for v in out] == [True]
