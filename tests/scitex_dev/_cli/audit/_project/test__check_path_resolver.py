"""Tests for PS-182 — rolled-own local-state path resolver.

All fixtures are synthetic ``tmp_path`` repos with a ``src/<pkg>/`` tree —
never the real peer packages. No mocks (NM001-003): real temp files.
Single observable per test (one assert).

The fixtures deliberately mirror the four real shapes surveyed when the
rule was designed:

  * scitex-todo / scitex-security ``_paths.py`` — a ``.git``-root walk +
    ``.scitex/<pkg>`` literal, no ``local_state`` import  → MUST fire.
  * scitex-agent-container snapshot ``_paths.py`` — delegates to
    ``scitex_config._ecosystem.local_state``                → MUST NOT fire.
  * scitex-app ``paths.py`` — ``$SCITEX_BASE_DIR`` env var, no ``.git``
    walk, no ``.scitex`` literal                            → MUST NOT fire.
  * scitex-dev — no ``_paths.py`` at all                    → MUST NOT fire.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_path_resolver import (
    check_ps182_rolled_own_path_resolver,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== helpers =====


def _findings(repo: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_ps182_rolled_own_path_resolver(repo, _StubViolation, out)
    return out


def _write(repo: Path, rel: str, text: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# A minimal rolled-own resolver: `.git` sentinel walk + `.scitex/<pkg>`
# project-scope literal, no canonical helper (scitex-todo shape).
_ROLLED_OWN = '''\
"""Task-store path resolution."""
import os
from pathlib import Path

PKG_SHORT = "todo"


def _find_git_root(start):
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return None


def resolve_tasks_path():
    git_root = _find_git_root(Path.cwd())
    if git_root is not None:
        project = git_root / ".scitex" / PKG_SHORT / "tasks.yaml"
        if project.exists():
            return project
    base = os.environ.get("SCITEX_DIR", str(Path.home() / ".scitex"))
    return Path(base) / PKG_SHORT / "tasks.yaml"
'''

# Uses the canonical helper (scitex-agent-container snapshot shape).
_USES_LOCAL_STATE = '''\
"""Snapshot cache paths — delegates precedence to local_state."""
from pathlib import Path


def cache_dir() -> Path:
    from scitex_config._ecosystem import local_state as _local_state
    return _local_state.runtime_path("agent-container", "cache")
'''

# A `.git`-root walk that resolves a NON-local-state path (no `.scitex`
# literal anywhere — not even a user-root fallback). Rolls its own root
# finding but has nothing to do with the `.scitex` tree, so PS-182 must
# stay silent (the `.scitex` literal is the second, load-bearing guard).
_GIT_WALK_NO_SCITEX = '''\
"""Locate the repo-root build dir."""
from pathlib import Path


def _find_git_root(start):
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return None


def build_dir():
    root = _find_git_root(Path.cwd()) or Path.cwd()
    return root / "build" / "artifacts"
'''

# Env-var-only resolver, no `.git` walk, no `.scitex` literal (scitex-app).
_ENV_ONLY = '''\
"""Reusable path resolution for SciTeX apps."""
import os
from pathlib import Path


def get_base_dir(base_dir=None) -> Path:
    if base_dir is not None:
        return Path(base_dir).resolve()
    env = os.environ.get("SCITEX_BASE_DIR")
    if env:
        return Path(env).resolve()
    raise ValueError("No base directory")
'''


# ===== 1. rolled-own resolver fires =====


class TestRolledOwnFires:
    def test_rolled_own_resolver_fires(self, tmp_path: Path) -> None:
        # Arrange
        _write(tmp_path, "src/scitex_todo/_paths.py", _ROLLED_OWN)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any(v.rule == "PS-182" for v in out)

    def test_violation_points_at_the_resolver_file(self, tmp_path: Path) -> None:
        # Arrange
        _write(tmp_path, "src/scitex_todo/_paths.py", _ROLLED_OWN)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out and out[0].where.endswith("_paths.py")

    def test_git_is_dir_sentinel_form_also_fires(self, tmp_path: Path) -> None:
        # Arrange — `.is_dir()` instead of `.exists()` (scitex-security shape)
        text = _ROLLED_OWN.replace('.git").exists()', '.git").is_dir()')
        _write(tmp_path, "src/scitex_security/_paths.py", text)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any(v.rule == "PS-182" for v in out)

    def test_bare_paths_py_name_also_scanned(self, tmp_path: Path) -> None:
        # Arrange — file named `paths.py` (no leading underscore)
        _write(tmp_path, "src/scitex_todo/paths.py", _ROLLED_OWN)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any(v.rule == "PS-182" for v in out)


# ===== 2. canonical-helper user is exempt =====


class TestCanonicalHelperExempt:
    def test_local_state_user_does_not_fire(self, tmp_path: Path) -> None:
        # Arrange
        _write(
            tmp_path,
            "src/scitex_agent_container/_paths.py",
            _USES_LOCAL_STATE,
        )
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== 3. env-var-only resolver is exempt (no .git walk, no .scitex) =====


class TestEnvOnlyExempt:
    def test_env_var_only_resolver_does_not_fire(self, tmp_path: Path) -> None:
        # Arrange
        _write(tmp_path, "src/scitex_app/paths.py", _ENV_ONLY)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== 4. clean repo (no resolver file) is exempt =====


class TestNoResolverFile:
    def test_repo_without_paths_file_does_not_fire(self, tmp_path: Path) -> None:
        # Arrange — a src tree with ordinary modules, no _paths.py/paths.py
        _write(tmp_path, "src/scitex_dev/_core.py", "x = 1\n")
        _write(tmp_path, "src/scitex_dev/cli.py", "y = 2\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []

    def test_missing_src_dir_does_not_crash(self, tmp_path: Path) -> None:
        # Arrange — no src/ at all
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== 5. low-false-positive guard: git walk WITHOUT .scitex literal =====


class TestGitWalkWithoutScitexLiteral:
    def test_git_walk_but_no_scitex_project_scope_does_not_fire(
        self, tmp_path: Path
    ) -> None:
        # Arrange — walks to a git root but resolves a NON-.scitex path
        # (a repo-relative build dir, no `.scitex` literal at all).
        _write(tmp_path, "src/scitex_thing/_paths.py", _GIT_WALK_NO_SCITEX)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== 6. violation shape =====


class TestViolationShape:
    def test_rule_code_is_ps_182(self, tmp_path: Path) -> None:
        # Arrange
        _write(tmp_path, "src/scitex_todo/_paths.py", _ROLLED_OWN)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert all(v.rule == "PS-182" for v in out)

    def test_detail_cites_user_path_fix(self, tmp_path: Path) -> None:
        # Arrange
        _write(tmp_path, "src/scitex_todo/_paths.py", _ROLLED_OWN)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out and "user_path()" in out[0].detail
