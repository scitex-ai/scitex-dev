"""Behavioural tests for `scitex-dev ecosystem audit-all`.

The command shells out to a real `scitex-dev` binary for each per-target
auditor. To exercise the dispatch deterministically without mocks, these
tests drop a real executable named `scitex-dev` earlier on PATH that
records its invocation and returns a controlled exit code / output. This
keeps the no-mocks rule: the audit-all process really forks subprocesses,
they're just pointed at a stub binary we own.

Covers:
  * the command module imports cleanly (PS-202 seed),
  * every audit still runs and is reported,
  * the final per-audit summary order is deterministic (= the fixed
    `audits` list order), independent of completion order,
  * the aggregate exit code is non-zero iff any one audit fails, and
  * runs the remaining audits even when one fails.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


_AUDITS = [
    "audit-cli",
    "audit-mcp-tools",
    "audit-skills",
    "audit-python-apis",
    "audit-project",
]


def test_audit_all_module_imports_cleanly() -> None:
    """The audit-all CLI command module must import without side-effects."""
    # Arrange
    module_name = "scitex_dev._cli.ecosystem._cmds._audit_all"
    import importlib

    # Act
    mod = importlib.import_module(module_name)
    # Assert
    assert mod.__name__ == module_name


# --------------------------------------------------------------------- #
# Fake-binary harness                                                    #
# --------------------------------------------------------------------- #


def _write_fake_scitex_dev(bin_dir: Path, sleep_map: dict) -> None:
    """Write an executable `scitex-dev` stub onto `bin_dir`.

    `sleep_map` maps an audit name -> (sleep_seconds, exit_code) so a test
    can force a non-trivial completion order and per-audit exit codes.
    """
    body = f"""#!/usr/bin/env python3
import sys, time, json
sleep_map = {sleep_map!r}
argv = sys.argv[1:]
# The launcher is now `<python> -m scitex_dev ecosystem audit-<name> <pkg>`,
# so strip the module-execution prefix before reading the audit name.
if argv[:2] == ["-m", "scitex_dev"]:
    argv = argv[2:]
# argv looks like: ecosystem audit-<name> <pkg> [--json] [--severity X]
audit = argv[1] if len(argv) > 1 else ""
delay, code = sleep_map.get(audit, (0.0, 0))
time.sleep(delay)
if "--json" in argv:
    print(json.dumps({{"violations": [] if code == 0 else [{{"rule": "X"}}]}}))
else:
    sys.stdout.write(f"STDOUT::{{audit}}\\n")
    sys.stderr.write(f"STDERR::{{audit}}\\n")
sys.exit(code)
"""
    script = bin_dir / "scitex-dev"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_audit_all(args, *, bin_dir: Path, sleep_map=None):
    """Invoke `ecosystem audit-all` with a fake scitex-dev on PATH."""
    _write_fake_scitex_dev(bin_dir, sleep_map or {})
    script = bin_dir / "scitex-dev"

    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    runner = CliRunner()
    # PATH is still shimmed, deliberately: `audit-all` MUST NOT consult it
    # any more (sac's P1 — one repo's audit resolved through a wrapper into
    # another repo's venv), and leaving the shim here means an accidental
    # regression to `shutil.which` keeps these tests green while the
    # dedicated hostile-PATH test is the one that fails. That is where the
    # signal belongs.
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    # The auditor is selected by pointing the INTERPRETER at the stub,
    # because the launcher is now `sys.executable -m scitex_dev`. Naming it
    # here rather than smuggling it through the environment is the same
    # discipline the fix itself enforces.
    # `_audit_all` imports sys INSIDE the command function, so there is no
    # module attribute to patch — the local `import sys as _sys` binds the
    # real module, and patching `sys.executable` therefore reaches it.
    import sys as _sys

    saved = _sys.executable
    _sys.executable = str(script)
    try:
        return runner.invoke(
            main,
            ["ecosystem", "audit-all", *args, "--no-version-check"],
            env=env,
            catch_exceptions=False,
        )
    finally:
        _sys.executable = saved


@pytest.mark.parametrize("audit", _AUDITS)
def test_every_audit_header_is_reported(tmp_path, audit):
    """Each audit runs as a subprocess and its header is reported."""
    # Arrange
    args = ["scitex-io"]
    # Act
    result = _run_audit_all(args, bin_dir=tmp_path)
    # Assert
    assert f"=== {audit} ===" in result.output


@pytest.mark.parametrize("audit", _AUDITS)
def test_every_audit_stdout_is_captured(tmp_path, audit):
    """Each audit's captured stdout is surfaced in the report."""
    # Arrange
    args = ["scitex-io"]
    # Act
    result = _run_audit_all(args, bin_dir=tmp_path)
    # Assert
    assert f"STDOUT::{audit}" in result.output


def test_summary_order_is_deterministic(tmp_path):
    """Headers follow the fixed declared order, not completion order."""
    # Arrange: make the first-declared audit finish last and vice versa.
    sleep_map = {
        "audit-cli": (0.40, 0),
        "audit-mcp-tools": (0.30, 0),
        "audit-skills": (0.20, 0),
        "audit-python-apis": (0.10, 0),
        "audit-project": (0.00, 0),
    }
    # Act
    result = _run_audit_all(
        ["scitex-io", "--audit-jobs", "0"], bin_dir=tmp_path, sleep_map=sleep_map
    )
    positions = [result.output.index(f"=== {a} ===") for a in _AUDITS]
    # Assert
    assert positions == sorted(positions)


def test_exit_code_zero_when_all_pass(tmp_path):
    """Aggregate exit code is 0 when every audit passes."""
    # Arrange
    args = ["scitex-io"]
    # Act
    result = _run_audit_all(args, bin_dir=tmp_path)
    # Assert
    assert result.exit_code == 0


def test_exit_code_nonzero_when_one_audit_fails(tmp_path):
    """Aggregate exit code is non-zero when a single audit fails."""
    # Arrange: only audit-skills fails.
    sleep_map = {a: (0.0, 0) for a in _AUDITS}
    sleep_map["audit-skills"] = (0.0, 1)
    # Act
    result = _run_audit_all(["scitex-io"], bin_dir=tmp_path, sleep_map=sleep_map)
    # Assert
    assert result.exit_code != 0


@pytest.mark.parametrize("audit", _AUDITS)
def test_remaining_audits_still_reported_when_one_fails(tmp_path, audit):
    """One failing audit doesn't suppress the others' reporting."""
    # Arrange: audit-cli fails; all others pass.
    sleep_map = {a: (0.0, 0) for a in _AUDITS}
    sleep_map["audit-cli"] = (0.0, 1)
    # Act
    result = _run_audit_all(["scitex-io"], bin_dir=tmp_path, sleep_map=sleep_map)
    # Assert
    assert f"=== {audit} ===" in result.output


# --------------------------------------------------------------------------- #
# The --new-only call site must agree with the callees


# --------------------------------------------------------------------------- #
# The --new-only call site must agree with the callee's signature              #
#                                                                              #
# v0.55.0 shipped NameError: name "scitex_dev_bin" is not defined here, and    #
# took the REQUIRED audit leg down in every repo that resolved it (the audit   #
# floor is >=0.17.14, a floor and not a pin). The dispatcher's binary lookup   #
# had been renamed to an argv and ONE of its two uses was updated.             #
#                                                                              #
# Nothing executed that line, so nothing failed. These read the call site out  #
# of the source and bind it against the real signature: cheap, and it catches  #
# the whole defect class -- any keyword drift between the two, not this name.  #
# --------------------------------------------------------------------------- #


def _new_only_call_keywords():
    """Keyword names `_audit_all` passes to `run_new_only_and_exit`. Pure."""
    import ast
    import pathlib

    from scitex_dev._cli.ecosystem._cmds import _audit_all as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name == "run_new_only_and_exit":
            return [kw.arg for kw in node.keywords if kw.arg is not None]
    return None


def test_the_new_only_call_site_is_present():
    # Arrange
    keywords = _new_only_call_keywords()
    # Act
    found = keywords is not None
    # Assert
    assert found


def test_the_new_only_call_site_binds_to_the_signature():
    # Arrange
    import inspect

    from scitex_dev._cli.ecosystem._cmds._audit_all_new_only import (
        run_new_only_and_exit,
    )

    keywords = _new_only_call_keywords()
    # Act — bind_partial raises TypeError on an unexpected keyword.
    bound = inspect.signature(run_new_only_and_exit).bind_partial(
        **{name: object() for name in keywords}
    )
    # Assert
    assert set(bound.arguments) == set(keywords)


def test_the_new_only_call_site_passes_an_argv_not_a_bin():
    # Arrange — the dispatcher resolves [sys.executable, "-m", "scitex_dev"]
    # so the audit runs where the console script is absent from PATH.
    keywords = _new_only_call_keywords()
    # Act
    passes_argv = "scitex_dev_argv" in keywords
    # Assert
    assert passes_argv
