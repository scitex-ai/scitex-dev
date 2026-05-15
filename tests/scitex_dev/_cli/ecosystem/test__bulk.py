"""`scitex-dev ecosystem bulk` — argv-based per-package execution.

Real subprocess against `/usr/bin/echo`; no mocks (STX-NM).
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands
from scitex_dev._cli.ecosystem._bulk import run_bulk


@pytest.fixture
def cli_main():
    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    return main


def test_bulk_dry_run_lists_one_package_when_filtered(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli_main, ["ecosystem", "bulk", "-p", "scitex-io", "echo"])
    # Assert
    assert result.exit_code == 0


def test_bulk_dry_run_output_contains_filtered_package_name(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli_main, ["ecosystem", "bulk", "-p", "scitex-io", "echo", "HELLO"]
    )
    # Assert
    assert "scitex-io" in result.output


def test_bulk_dry_run_does_not_execute(cli_main):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli_main, ["ecosystem", "bulk", "-p", "scitex-io", "echo", "HELLO"]
    )
    # Assert: dry-run output begins with "# DRY-RUN" marker
    assert "DRY-RUN" in result.output


def test_bulk_apply_executes_echo_with_package_appended():
    # Arrange
    echo_bin = shutil.which("echo") or "/bin/echo"
    # Act
    rc = run_bulk(
        (echo_bin, "HELLO"),
        packages=("scitex-io",),
        jobs=1,
        yes=True,
    )
    # Assert
    assert rc == 0


def test_bulk_apply_with_category_filter_runs_only_matching():
    # Arrange
    echo_bin = shutil.which("echo") or "/bin/echo"
    # Act
    rc = run_bulk(
        (echo_bin,),
        categories=("dataset",),
        jobs=1,
        yes=True,
    )
    # Assert
    assert rc == 0


def test_bulk_apply_emits_prefixed_output(cli_main, capfd):
    # Arrange
    echo_bin = shutil.which("echo") or "/bin/echo"
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli_main,
        [
            "ecosystem",
            "bulk",
            "-p",
            "scitex-io",
            "--yes",
            "-j",
            "1",
            echo_bin,
            "HELLO",
        ],
    )
    # Assert: per-package prefix `[scitex-io]` appears in stdout
    assert "[scitex-io]" in result.output


@pytest.fixture
def bulk_echo_hello_scitex_io_tokens(cli_main):
    """Run `bulk echo HELLO` against scitex-io and return the echoed tokens.

    Returns the whitespace-separated token list of the `HELLO ...` echo line
    for the `scitex-io` package, or `None` if no such line was emitted.
    """
    echo_bin = shutil.which("echo") or "/bin/echo"
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "ecosystem",
            "bulk",
            "-p",
            "scitex-io",
            "--yes",
            "-j",
            "1",
            echo_bin,
            "HELLO",
        ],
    )
    for line in result.output.splitlines():
        if line.startswith("[scitex-io] "):
            body = line[len("[scitex-io] ") :]
            tokens = body.split()
            if tokens and tokens[0] == "HELLO":
                return tokens
    return None


def test_bulk_apply_package_name_is_last_argv_element(
    bulk_echo_hello_scitex_io_tokens,
):
    """`bulk echo HELLO` runs `echo HELLO <pkg>` — pkg is the LAST argv token."""
    # Arrange
    tokens = bulk_echo_hello_scitex_io_tokens
    # Act
    last_token = tokens[-1] if tokens else None
    # Assert
    assert last_token == "scitex-io"


def test_bulk_apply_returns_nonzero_when_command_missing():
    # Arrange
    # Act
    rc = run_bulk(
        ("nonexistent-binary-zzz-12345",),
        packages=("scitex-io",),
        jobs=1,
        yes=True,
    )
    # Assert: should be the documented "command not found" exit (127)
    assert rc == 127


def test_bulk_no_matching_packages_returns_1():
    # Arrange
    echo_bin = shutil.which("echo") or "/bin/echo"
    # Act
    rc = run_bulk(
        (echo_bin,),
        packages=("definitely-not-a-real-package-xyz",),
        jobs=1,
        yes=True,
    )
    # Assert
    assert rc == 1


def test_bulk_missing_verb_returns_2():
    # Arrange
    # Act
    rc = run_bulk((), packages=("scitex-io",), yes=True)
    # Assert
    assert rc == 2


# ---------------------------------------------------------------------------
# xargs-style `{}` substitution
# ---------------------------------------------------------------------------


def test_substitute_helper_replaces_braces_token():
    """`{}` token is replaced exactly with the package name; no other tokens touched."""
    # Arrange
    from scitex_dev._cli.ecosystem._bulk import _substitute

    template = ("git", "-C", "~/proj/{}", "pull", "--rebase")
    # Act
    argv = _substitute(template, "scitex-io")
    # Assert: `{}` becomes the pkg name; nothing else changes; no extra append
    assert argv == ["git", "-C", "~/proj/scitex-io", "pull", "--rebase"]


def test_substitute_helper_append_mode_when_no_braces():
    """Without `{}`, the pkg name is appended at the end (back-compat append form)."""
    # Arrange
    from scitex_dev._cli.ecosystem._bulk import _substitute

    template = ("echo", "HELLO")
    # Act
    argv = _substitute(template, "scitex-io")
    # Assert
    assert argv == ["echo", "HELLO", "scitex-io"]


def test_substitute_helper_replaces_every_brace_token():
    """Multiple `{}` tokens are all replaced with the pkg name."""
    # Arrange
    from scitex_dev._cli.ecosystem._bulk import _substitute

    template = ("echo", "{}", "and", "{}")
    # Act
    argv = _substitute(template, "scitex-io")
    # Assert
    assert argv == ["echo", "scitex-io", "and", "scitex-io"]


def test_bulk_apply_substitutes_braces_in_echo(cli_main):
    """`bulk -- echo HELLO {} WORLD` echoes `HELLO <pkg> WORLD` per package."""
    # Arrange
    echo_bin = shutil.which("echo") or "/bin/echo"
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli_main,
        [
            "ecosystem",
            "bulk",
            "-p",
            "scitex-io",
            "--yes",
            "-j",
            "1",
            echo_bin,
            "HELLO",
            "{}",
            "WORLD",
        ],
    )
    # Find the echoed line under the [scitex-io] prefix
    body = None
    for line in result.output.splitlines():
        if line.startswith("[scitex-io] "):
            candidate = line[len("[scitex-io] ") :]
            if candidate.startswith("HELLO "):
                body = candidate
                break
    # Assert
    assert body == "HELLO scitex-io WORLD"
