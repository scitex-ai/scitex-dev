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
