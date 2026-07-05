"""Tests for ``scitex-dev trace-env-vars`` — static scan + redaction.

Correctness the tool hinges on:

* WORD-BOUNDARY matching — searching ``FOO`` must NOT match ``FOO_BAR``
  (the operator's real pitfall: ``SCITEX_TODO_AGENT`` vs
  ``SCITEX_TODO_AGENT_ID``).
* An assignment in a temp rc file is found with correct ``file:line``.
* A currently-set var is detected.
* Secret-shaped values are redacted in ALL output.
* Graceful behaviour when tmux / strace are absent.
* ``--json`` output shape.

Scan-surface tests inject a temp ``home``/``environ`` so they never
read the real ``$HOME``. Env-dependent CLI tests use yield-based
fixtures that mutate the real environment and restore it on teardown
(no ``monkeypatch``, per the ecosystem NM002 rule).
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main
from scitex_dev.trace_env import (
    assignment_regex,
    is_secret_shaped,
    redact,
    scan_env_vars,
    trace_env_vars,
)
from scitex_dev.trace_env.trace import _result_from_trace


# --------------------------------------------------------------------
# Fixtures — real-environment mutation with restore-on-teardown.
# --------------------------------------------------------------------


@pytest.fixture
def cli_var():
    # Arrange: set a real env var, restore on teardown.
    key = "MY_CLI_TRACE_VAR"
    prior = os.environ.get(key)
    os.environ[key] = "v1"
    yield key
    if prior is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = prior


@pytest.fixture
def empty_path(tmp_path):
    # Arrange: point PATH at an empty dir so shutil.which finds nothing.
    empty = tmp_path / "emptybin"
    empty.mkdir()
    prior = os.environ.get("PATH")
    os.environ["PATH"] = str(empty)
    yield
    if prior is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = prior


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
# WORD-BOUNDARY correctness — the key pitfall of this tool.
# --------------------------------------------------------------------


def test_assignment_regex_matches_bare_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO=1")
    # Assert
    assert hit


def test_assignment_regex_matches_export_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("export FOO=1")
    # Assert
    assert hit


def test_assignment_regex_matches_spaced_assignment():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO = 1")
    # Assert
    assert hit


def test_assignment_regex_rejects_longer_suffix_identifier():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO_BAR=1")
    # Assert
    assert not hit


def test_assignment_regex_rejects_longer_prefix_identifier():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("PREFIX_FOO=1")
    # Assert
    assert not hit


def test_assignment_regex_rejects_equality_comparison():
    # Arrange
    rx = assignment_regex("FOO")
    # Act
    hit = rx.search("FOO==1")
    # Assert
    assert not hit


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
# Redaction — secret-shaped values never printed.
# --------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["API_KEY", "GH_TOKEN", "DB_PASSWORD", "MY_PASS", "X_SECRET",
     "AWS_CREDENTIAL", "SOME_AUTH", "A_COOKIE", "SCITEX_TODO_SESSION"],
)
def test_is_secret_shaped_true(name):
    # Arrange
    # Act
    shaped = is_secret_shaped(name)
    # Assert
    assert shaped


@pytest.mark.parametrize("name", ["SCITEX_TODO_AGENT", "PATH", "HOME", "KEYBOARD"])
def test_is_secret_shaped_false(name):
    # Arrange
    # Act
    shaped = is_secret_shaped(name)
    # Assert
    assert not shaped


def test_redact_replaces_secret_value():
    # Arrange
    # Act
    out = redact("API_KEY", "supersecret")
    # Assert
    assert out == "<redacted: 11 chars>"


def test_redact_passes_through_nonsecret_value():
    # Arrange
    # Act
    out = redact("PATH", "/usr/bin")
    # Assert
    assert out == "/usr/bin"


def test_redact_passes_through_none():
    # Arrange
    # Act
    out = redact("API_KEY", None)
    # Assert
    assert out is None


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
# Graceful degradation — tmux / strace absence.
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


def test_trace_error_message_when_strace_missing(empty_path):
    # Arrange
    # Act
    result = trace_env_vars(["FOO"], command=["echo", "hi"])
    # Assert
    assert "strace is required" in (result.error or "")


def test_trace_mode_is_trace_when_strace_missing(empty_path):
    # Arrange
    # Act
    result = trace_env_vars(["FOO"], command=["echo", "hi"])
    # Assert
    assert result.mode == "trace"


def test_trace_empty_output_is_inconclusive_not_var_absent():
    # Arrange: strace produced ZERO execve records (ptrace denied).
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert "inconclusive" in (result.error or "")


def test_trace_empty_output_disclaims_var_not_found():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert "not found" in (result.error or "")


def test_trace_empty_output_reports_zero_stages():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert result.exec_stages == 0


def test_trace_empty_output_has_no_hits():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert result.trace_hits == []


def test_trace_empty_output_surfaces_ptrace_hint():
    # Arrange
    stderr = "strace: ptrace(PTRACE_TRACEME, ...): Operation not permitted\n"
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text=stderr)
    # Assert
    assert "strace said:" in (result.error or "")


def test_trace_nonempty_output_locates_var():
    # Arrange: a synthetic execve record carrying FOO.
    raw = 'execve("/bin/x", ["x"], ["PATH=/bin", "FOO=bar"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.trace_hits[0].var == "FOO"


def test_trace_nonempty_output_has_no_error():
    # Arrange
    raw = 'execve("/bin/x", ["x"], ["FOO=bar"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.error is None


def test_trace_nonempty_but_var_absent_is_not_inconclusive():
    # Arrange: strace worked (a stage parsed) but FOO is not in it.
    raw = 'execve("/bin/x", ["x"], ["PATH=/bin"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.error is None


# --------------------------------------------------------------------
# CLI wiring + --json output shape.
# --------------------------------------------------------------------


def test_cli_scan_exit_code_zero(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux"]
    )
    # Assert
    assert result.exit_code == 0, result.output


def test_cli_scan_mentions_var(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux"]
    )
    # Assert
    assert cli_var in result.output


def test_cli_json_mode_field(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["mode"] == "scan"


def test_cli_json_variable_name(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["variables"][0]["name"] == cli_var


def test_cli_json_currently_set(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "--json"]
    )
    # Assert
    assert json.loads(result.output)["variables"][0]["currently_set"] is True


def test_cli_quiet_one_line_summary(cli_var):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["trace-env-vars", cli_var, "--no-etc", "--no-tmux", "-q"]
    )
    # Assert
    assert result.output.startswith("scan:")


# --------------------------------------------------------------------
# Dynamic trace (--trace) — CLI passthrough split + exec-stage locate.
# Skipped where strace is unavailable (e.g. some CI runners).
# --------------------------------------------------------------------


_NEEDS_STRACE = pytest.mark.skipif(
    shutil.which("strace") is None, reason="strace not installed"
)


@_NEEDS_STRACE
def test_cli_trace_locates_var_injected_at_inner_exec_stage():
    # Arrange: `sh -c` injects TRACE_ME then execs `env true`, so the
    # var first appears at the inner exec — the command tokens after
    # `--` must be split off from the traced NAME.
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main,
        [
            "trace-env-vars",
            "TRACE_ME_XYZ",
            "--trace",
            "--json",
            "--",
            "sh",
            "-c",
            "TRACE_ME_XYZ=injected exec env true",
        ],
    )
    # Assert
    assert json.loads(result.output)["trace_hits"], result.output


@_NEEDS_STRACE
def test_cli_trace_splits_command_from_names():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main,
        [
            "trace-env-vars",
            "TRACE_ME_XYZ",
            "--trace",
            "--json",
            "--",
            "sh",
            "-c",
            "TRACE_ME_XYZ=injected exec env true",
        ],
    )
    # Assert
    assert [v["name"] for v in json.loads(result.output)["variables"]] == [
        "TRACE_ME_XYZ"
    ]


# EOF
