"""Tests for PS-181 — `~/.scitex/<pkg>/` registry-layout conformance.

Unlike sibling PS-1xx checks (repo-scoped), this rule inspects a whole
``$SCITEX_DIR`` tree of ``<pkg>/`` state directories. All fixtures here
are synthetic ``tmp_path`` trees — never the real ``~/.scitex``.

No mocks (NM001-003) — real temp dirs. Single assert per test (PA-307
§3 STX-TQ007 — one observable per test).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_registry_layout import (
    check_registry_layout,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== helpers =====


def _findings(scitex_dir: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_registry_layout(scitex_dir, _StubViolation, out)
    return out


def _make_conformant_pkg(scitex_dir: Path, pkg: str = "conformant_pkg") -> Path:
    pkg_dir = scitex_dir / pkg
    (pkg_dir / "runtime").mkdir(parents=True)
    (pkg_dir / "logs").mkdir()
    (pkg_dir / "archive" / "20260601").mkdir(parents=True)
    (pkg_dir / "bin").mkdir()
    (pkg_dir / "agents" / "alpha").mkdir(parents=True)
    (pkg_dir / "config.yaml").write_text("key: value\n")
    (pkg_dir / "agents" / "alpha" / "spec.yaml").write_text("role: worker\n")
    return pkg_dir


# ===== 1. config.yaml XOR config/ =====


class TestConfigBoth:
    def test_config_yaml_and_config_dir_both_present_fires(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        pkg_dir = tmp_path / "dual_config_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "config.yaml").write_text("a: 1\n")
        (pkg_dir / "config").mkdir()
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("both `config.yaml` and `config/`" in v.detail for v in out)


class TestConfigWrongNameAlone:
    def test_only_differently_named_config_file_fires(self, tmp_path: Path) -> None:
        # Arrange — dashboard.yaml only, no config.yaml/config/.
        pkg_dir = tmp_path / "misnamed_config_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "dashboard.yaml").write_text("a: 1\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("dashboard.yaml" in v.detail for v in out)


# ===== 2. loose runtime-state files =====


class TestLooseRuntimeState:
    def test_loose_pid_file_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "runtime_state_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text("12345\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("board.pid" in v.detail for v in out)

    def test_loose_ci_state_json_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "runtime_state_pkg2"
        pkg_dir.mkdir()
        (pkg_dir / "ci-state.json").write_text("{}\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("ci-state.json" in v.detail for v in out)


# ===== 3. loose *.log =====


class TestLooseLog:
    def test_loose_log_file_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "log_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "debug.log").write_text("boot\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("debug.log" in v.detail for v in out)


# ===== 4. archive naming =====


class TestArchiveNaming:
    def test_underscore_archive_date_dir_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "archive_pkg"
        (pkg_dir / "_archive-20260617").mkdir(parents=True)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("_archive-20260617" in v.detail for v in out)

    def test_bak_dated_file_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "archive_pkg2"
        pkg_dir.mkdir()
        (pkg_dir / "tasks.yaml.bak-20260601").write_text("old\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("tasks.yaml.bak-20260601" in v.detail for v in out)


# ===== 5. __pycache__ / build artifacts =====


class TestBuildArtifact:
    def test_top_level_pycache_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pycache_pkg"
        (pkg_dir / "__pycache__").mkdir(parents=True)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("__pycache__" in v.detail for v in out)


# ===== 6. loose scripts =====


class TestLooseScript:
    def test_loose_py_file_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "script_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "cleanup.py").write_text("# script\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("cleanup.py" in v.detail for v in out)


# ===== 7. venv naming =====


class TestVenvNaming:
    def test_wrongly_named_venv_dir_with_pyvenv_cfg_fires(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "venv_pkg"
        venv = pkg_dir / "board-venv"
        venv.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert any("board-venv" in v.detail for v in out)

    def test_canonical_venvs_dir_with_pyvenv_cfg_no_fire(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "venv_pkg2"
        venv = pkg_dir / "venvs" / "board"
        venv.mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any("venv" in v.detail.lower() for v in out)

    def test_random_dir_without_pyvenv_cfg_no_fire(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "venv_pkg3"
        (pkg_dir / "random-stuff").mkdir(parents=True)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-181" for v in out)


# ===== 8. no false positives on a conformant package =====


class TestConformantPackage:
    def test_fully_conformant_package_has_zero_violations(self, tmp_path: Path) -> None:
        # Arrange
        _make_conformant_pkg(tmp_path)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== domain-authored content is never flagged =====


class TestDomainContentExempt:
    def test_files_inside_agents_dir_never_flagged(self, tmp_path: Path) -> None:
        # Arrange — an oddly-named file living INSIDE agents/ should be ignored
        # (the rule never recurses into domain-authored subdirectories).
        pkg_dir = tmp_path / "domain_pkg"
        agents = pkg_dir / "agents" / "alpha"
        agents.mkdir(parents=True)
        (agents / "debug.log").write_text("nested, should be ignored\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert out == []


# ===== violation shape =====


class TestViolationShape:
    def test_violation_rule_code_is_ps_181(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "rule_code_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "debug.log").write_text("x\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert all(v.rule == "PS-181" for v in out)
