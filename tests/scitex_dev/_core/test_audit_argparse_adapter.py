"""Real lazy Click and argparse entry points must be captured without running."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import click
import pytest

from scitex_dev._cli.audit._summary._audit import _capture_root
from scitex_dev._core.audit_argparse_adapter import (
    StopBeforeParse,
    intercept_parse_calls,
)


def test_lazy_click_group_is_captured_before_its_callback():
    # Arrange
    invoked = []
    group = click.Group("owned-tool", callback=lambda: invoked.append(True))

    def lazy_main():
        group.main(args=[], standalone_mode=False)

    # Act
    captured = _capture_root(lazy_main)
    # Assert
    assert (captured, invoked) == (group, [])


def test_click_method_owners_are_restored_after_an_exception():
    # Arrange
    owners = {
        next(base for base in cls.__mro__ if "main" in base.__dict__)
        for cls in (click.Command, click.Group)
    }
    before = {owner: owner.__dict__["main"] for owner in owners}
    # Act
    caught = None
    try:
        with intercept_parse_calls([]):
            raise RuntimeError("owned failure")
    except RuntimeError as error:
        caught = str(error)
    after = {owner: owner.__dict__["main"] for owner in owners}
    # Assert
    assert (after, caught) == (before, "owned failure")


@pytest.mark.parametrize("method", ("parse_args", "parse_known_args"))
def test_argparse_capture_remains_available(method):
    # Arrange
    parser = argparse.ArgumentParser(prog="owned-parser")
    captured = []
    # Act
    intercepted = False
    try:
        with intercept_parse_calls(captured):
            getattr(parser, method)([])
    except StopBeforeParse:
        intercepted = True
    # Assert
    assert (captured, intercepted) == ([parser], True)


def test_real_console_distribution_resolves_a_lazy_click_entrypoint(
    tmp_path: Path,
):
    # Arrange: genuine importlib metadata, not a replacement entry-point API.
    (tmp_path / "owned_lazy_cli.py").write_text(
        "def main():\n"
        "    import click\n"
        '    click.Group("owned-lazy-tool").main(args=[], standalone_mode=False)\n'
    )
    distribution = tmp_path / "owned_lazy_tool-0.0.0.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text("Name: owned-lazy-tool\nVersion: 0.0.0\n")
    (distribution / "entry_points.txt").write_text(
        "[console_scripts]\nowned-lazy-tool = owned_lazy_cli:main\n"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(tmp_path), *sys.path])
    program = (
        "import click, json; "
        "from scitex_dev._cli.audit._summary._audit import _resolve_entry_point; "
        "command = _resolve_entry_point('owned-lazy-tool'); "
        "print(json.dumps([isinstance(command, click.Group), command.name]))"
    )
    # Act: a fresh real interpreter discovers the owned distribution.
    result = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    # Assert
    assert json.loads(result.stdout) == [True, "owned-lazy-tool"]
