"""Tests for ``scitex_dev.trace_env.scan`` — the static assignment scanner.

Exercises ``scan_env_vars`` end-to-end against injected temp ``home`` /
``environ`` (never the real ``$HOME``):

* WORD-BOUNDARY matching at the scan surface (``SCITEX_TODO_AGENT`` must not
  pick up ``SCITEX_TODO_AGENT_ID``).
* Assignment-site discovery (file / line / surface) across shell-init +
  direnv walk-up, plus currently-set detection.
* Secret-shaped value redaction in the emitted report.
* Graceful behaviour when tmux is absent.

The matching/redaction primitives are unit-tested in ``test_config.py``; the
CLI surface in ``tests/scitex_dev/_cli/test__trace_env.py``.
"""

from __future__ import annotations

import pytest

from scitex_dev.trace_env import scan_env_vars


# --------------------------------------------------------------------
# Fixtures — real-environment injection (temp home/environ, no monkeypatch).
# --------------------------------------------------------------------


@pytest.fixture
def agent_report(tmp_path):
    # Arrange: two vars, one a prefix of the other.
    (tmp_path / ".bashrc").write_text(
        "export SCITEX_TODO_AGENT=alpha\nexport SCITEX_TODO_AGENT_ID=beta\n"
    )
    result = scan_env_vars(
        ["SCITEX_TODO_AGENT"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    return result.variables[0]


@pytest.fixture
def zshrc_site(tmp_path):
    # Arrange: an assignment on line 3.
    rc = tmp_path / ".zshrc"
    rc.write_text("# comment\n\nexport MY_VAR=hello\n")
    result = scan_env_vars(
        ["MY_VAR"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    return rc, result.variables[0].assignments[0]


@pytest.fixture
def secret_report(tmp_path):
    # Arrange: a secret-shaped var set both in a file and live.
    (tmp_path / ".bashrc").write_text("export MY_API_KEY=abcdefgh\n")
    result = scan_env_vars(
        ["MY_API_KEY"],
        home=tmp_path,
        cwd=tmp_path,
        environ={"MY_API_KEY": "abcdefgh"},
        include_etc=False,
        include_tmux=False,
    )
    return result.variables[0]


# --------------------------------------------------------------------
# WORD-BOUNDARY correctness at the scan surface.
# --------------------------------------------------------------------


def test_scan_word_boundary_finds_single_site(agent_report):
    # Arrange
    # Act
    # Assert
    assert len(agent_report.assignments) == 1


def test_scan_word_boundary_site_on_correct_line(agent_report):
    # Arrange
    # Act
    # Assert
    assert agent_report.assignments[0].line == 1


def test_scan_word_boundary_matches_exact_var(agent_report):
    # Arrange
    # Act
    # Assert
    assert "SCITEX_TODO_AGENT=alpha" in agent_report.assignments[0].text


def test_scan_word_boundary_excludes_longer_var(agent_report):
    # Arrange
    # Act
    # Assert
    assert "AGENT_ID" not in agent_report.assignments[0].text


# --------------------------------------------------------------------
# Assignment site discovery + currently-set detection.
# --------------------------------------------------------------------


def test_scan_site_has_correct_file(zshrc_site):
    # Arrange
    # Act
    rc, site = zshrc_site
    # Assert
    assert site.file == str(rc)


def test_scan_site_has_correct_line(zshrc_site):
    # Arrange
    # Act
    _rc, site = zshrc_site
    # Assert
    assert site.line == 3


def test_scan_site_has_shell_init_surface(zshrc_site):
    # Arrange
    # Act
    _rc, site = zshrc_site
    # Assert
    assert site.surface == "shell-init"


def test_scan_detects_currently_set_flag(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MY_VAR"],
        home=tmp_path,
        cwd=tmp_path,
        environ={"MY_VAR": "live-value"},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].currently_set is True


def test_scan_reports_current_value(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MY_VAR"],
        home=tmp_path,
        cwd=tmp_path,
        environ={"MY_VAR": "live-value"},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].current_value == "live-value"


def test_scan_unset_var_not_set(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MISSING"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].currently_set is False


def test_scan_unset_var_value_none(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MISSING"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].current_value is None


def test_scan_unset_var_no_sites(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MISSING"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].assignments == []


def test_scan_finds_envrc_walking_up_site_count(tmp_path):
    # Arrange
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "a" / "b"
    project.mkdir(parents=True)
    (tmp_path / "a" / ".envrc").write_text("export PROJ_VAR=xyz\n")
    # Act
    result = scan_env_vars(
        ["PROJ_VAR"],
        home=home,
        cwd=project,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert len(result.variables[0].assignments) == 1


def test_scan_finds_envrc_walking_up_surface(tmp_path):
    # Arrange
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "a" / "b"
    project.mkdir(parents=True)
    (tmp_path / "a" / ".envrc").write_text("export PROJ_VAR=xyz\n")
    # Act
    result = scan_env_vars(
        ["PROJ_VAR"],
        home=home,
        cwd=project,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.variables[0].assignments[0].surface == "direnv"


# --------------------------------------------------------------------
# Redaction at the scan surface — secret-shaped values never printed.
# --------------------------------------------------------------------


def test_scan_redacts_current_secret_value(secret_report):
    # Arrange
    # Act
    # Assert
    assert secret_report.current_value == "<redacted: 8 chars>"


def test_scan_site_hides_secret_value(secret_report):
    # Arrange
    # Act
    # Assert
    assert "abcdefgh" not in secret_report.assignments[0].text


def test_scan_site_shows_redaction_marker(secret_report):
    # Arrange
    # Act
    # Assert
    assert "<redacted:" in secret_report.assignments[0].text


# --------------------------------------------------------------------
# Graceful degradation — tmux absence.
# --------------------------------------------------------------------


def test_scan_tmux_disabled_does_not_crash(tmp_path):
    # Arrange
    # Act
    result = scan_env_vars(
        ["MY_VAR"],
        home=tmp_path,
        cwd=tmp_path,
        environ={},
        include_etc=False,
        include_tmux=False,
    )
    # Assert
    assert result.tmux_available is False
