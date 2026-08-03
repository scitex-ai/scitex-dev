# -*- coding: utf-8 -*-
"""CLI-surface tests for ``scitex-dev dev secret``.

These cover the guarantees the LIBRARY cannot make on its own — that the
command layer keeps the value on stdout and everything else on stderr, that
--dry-run changes nothing, and that a passphrase is accepted by REFERENCE
(a file path) rather than on a command line where `ps` exposes it.

No mocking: the real Click group is invoked through CliRunner, and gpg is
really executed against a throwaway key.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from click.testing import CliRunner

from scitex_dev._cli._root import main

pytestmark = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg not installed")

_UID = "SciTeX CLI Throwaway <cli-throwaway@example.invalid>"


@pytest.fixture()
def gpg_env(tmp_path):
    """A throwaway GNUPGHOME plus an isolated store root, both restored after."""
    home = tmp_path / "g"
    home.mkdir(mode=0o700)
    store = tmp_path / "s"
    previous = {k: os.environ.get(k) for k in ("GNUPGHOME", "SCITEX_DEV_SECRET_ROOT")}
    os.environ["GNUPGHOME"] = str(home)
    os.environ["SCITEX_DEV_SECRET_ROOT"] = str(store)
    proc = subprocess.run(
        ["gpg", "--batch", "--quiet", "--passphrase", "", "--pinentry-mode",
         "loopback", "--quick-generate-key", _UID, "default", "default", "never"],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # gpg-agent's socket must fit ~108 chars; a long tmp path fails here.
        pytest.skip("throwaway key creation failed (often a too-long GNUPGHOME path)")
    yield store
    # gpg starts a gpg-agent DAEMON per GNUPGHOME and nothing reaps it when the
    # tmp dir is removed — measured 2026-08-03: agents from a finished run were
    # still alive 18 minutes later, one per test. Kill it explicitly, or a full
    # suite leaks a daemon for every test that touches gpg.
    subprocess.run(
        ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
        capture_output=True, check=False,
    )
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def initialised(gpg_env):
    CliRunner().invoke(main, ["dev", "secret", "init", "--recipient", _UID])
    return gpg_env


# ------------------------------------------------------------------ dry run

def test_dry_run_init_creates_no_store(gpg_env):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "init", "--recipient", _UID, "--dry-run"])
    # Assert
    assert not (gpg_env / ".gpg-id").exists()


def test_init_without_dry_run_does_create_the_store(gpg_env):
    """POSITIVE CONTROL: the dry-run assertion above is not vacuous."""
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "init", "--recipient", _UID])
    # Assert
    assert (gpg_env / ".gpg-id").is_file()


def test_dry_run_generate_stores_nothing(initialised):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "generate", "a/b", "--dry-run"])
    # Assert
    assert not (initialised / "a" / "b.gpg").exists()


# ------------------------------------------------- stdout / stderr contract

def test_show_puts_the_value_on_stdout(initialised):
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "generate", "svc/k", "--length", "20"])
    # Act
    result = runner.invoke(main, ["dev", "secret", "show", "svc/k"])
    # Assert
    assert len(result.stdout.strip()) == 20


def test_failing_show_puts_nothing_on_stdout(initialised):
    """The decrypt.sh defect, closed at the command boundary."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["dev", "secret", "show", "does/not/exist"])
    # Assert
    assert result.stdout == ""


def test_failing_show_exits_non_zero(initialised):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["dev", "secret", "show", "does/not/exist"])
    # Assert
    assert result.exit_code != 0


# ------------------------------------------------------------------- set

_ISSUED = "provider-issued-token-Xk29fQ"


def test_set_stores_a_value_from_stdin(initialised):
    """The whole point: a value we did NOT generate can be stored."""
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "set", "gitea/tok"], input=_ISSUED)
    # Assert
    assert (initialised / "gitea" / "tok.gpg").is_file()


def test_set_round_trips_the_exact_value(initialised):
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "set", "gitea/tok2"], input=_ISSUED)
    # Act
    result = runner.invoke(main, ["dev", "secret", "show", "gitea/tok2"])
    # Assert
    assert result.stdout == _ISSUED


def test_set_strips_a_trailing_newline_from_a_pipe(initialised):
    """A pasted token usually arrives with \\n; a stray \\n fails auth confusingly."""
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "set", "gitea/tok3"], input=_ISSUED + "\n")
    # Act
    result = runner.invoke(main, ["dev", "secret", "show", "gitea/tok3"])
    # Assert
    assert result.stdout == _ISSUED


def test_set_refuses_an_empty_value(initialised):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["dev", "secret", "set", "gitea/empty"], input="")
    # Assert
    assert result.exit_code != 0


def test_set_refusing_empty_writes_nothing(initialised):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "set", "gitea/empty2"], input="")
    # Assert
    assert not (initialised / "gitea" / "empty2.gpg").exists()


def test_set_reads_from_a_file(initialised, tmp_path):
    # Arrange
    runner = CliRunner()
    src = tmp_path / "token.txt"
    src.write_text(_ISSUED + "\n")
    # Act
    runner.invoke(main, ["dev", "secret", "set", "cf/tunnel", "--from-file", str(src)])
    # Assert
    assert runner.invoke(main, ["dev", "secret", "show", "cf/tunnel"]).stdout == _ISSUED


def test_set_with_a_missing_file_is_refused(initialised, tmp_path):
    # Arrange
    runner = CliRunner()
    absent = tmp_path / "no-such-token"
    # Act
    result = runner.invoke(main, ["dev", "secret", "set", "cf/x", "--from-file", str(absent)])
    # Assert
    assert result.exit_code != 0


def test_set_dry_run_stores_nothing(initialised):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["dev", "secret", "set", "d/r", "--dry-run"], input=_ISSUED)
    # Assert
    assert not (initialised / "d" / "r.gpg").exists()


def test_set_without_yes_refuses_to_overwrite(initialised):
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "set", "dup/tok"], input=_ISSUED)
    # Act
    result = runner.invoke(main, ["dev", "secret", "set", "dup/tok"], input="second")
    # Assert
    assert result.exit_code != 0


def test_set_with_yes_overwrites(initialised):
    """POSITIVE CONTROL: the refusal above is about consent, not about set being broken."""
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "set", "dup/tok2"], input=_ISSUED)
    # Act
    runner.invoke(main, ["dev", "secret", "set", "dup/tok2", "--yes"], input="second-value")
    # Assert
    assert runner.invoke(main, ["dev", "secret", "show", "dup/tok2"]).stdout == "second-value"


def test_set_does_not_accept_the_value_as_an_option(initialised):
    """The argv guarantee: there must be no --value flag to leak through `ps`."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["dev", "secret", "set", "argv/x", "--value", _ISSUED])
    # Assert
    assert "no such option" in result.output.lower()


def test_set_help_does_not_advertise_a_value_option(initialised):
    """CONTROL for the above: the help renders, so the absence is real."""
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["dev", "secret", "set", "--help"])
    # Assert
    assert "--from-file" in result.output


# ---------------------------------------------------------------- --json

def test_list_json_is_parseable(initialised):
    # Arrange
    import json
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "generate", "j/one"])
    # Act
    result = runner.invoke(main, ["dev", "secret", "list", "--json"])
    # Assert
    assert json.loads(result.stdout)["names"] == ["j/one"]


# --------------------------------------------------------- passphrase file

def test_missing_passphrase_file_is_refused(initialised, tmp_path):
    # Arrange
    runner = CliRunner()
    absent = tmp_path / "no-such-passphrase"
    # Act
    result = runner.invoke(main, ["dev", "secret", "create-backup", "--dest",
                                  str(tmp_path / "b.gpg"), "--passphrase-file", str(absent)])
    # Assert
    assert result.exit_code != 0


def test_backup_reads_the_passphrase_from_the_named_file(initialised, tmp_path):
    """POSITIVE CONTROL: a real passphrase file works, so the refusal is specific."""
    # Arrange
    runner = CliRunner()
    runner.invoke(main, ["dev", "secret", "generate", "b/one"])
    pp = tmp_path / "pp"
    pp.write_text("file-supplied-passphrase\n")
    dest = tmp_path / "backup.gpg"
    # Act
    runner.invoke(main, ["dev", "secret", "create-backup", "--dest", str(dest),
                         "--passphrase-file", str(pp)])
    # Assert
    assert dest.is_file()
