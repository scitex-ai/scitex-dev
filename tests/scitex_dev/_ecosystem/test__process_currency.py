#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_ecosystem/test__process_currency.py

"""A screen that never fires proves only that the loop ran.

Every test here plants a KNOWN answer — a process older than its package, a
process newer, an unreadable /proc — because the defect this module exists
to catch (an orphan serving pre-upgrade bytes) went undetected for hours
precisely because nothing disagreed with anything.

No mocks: `/proc` and the package root are injected as real directories
under tmp_path, so the parser is exercised against real bytes in the real
format rather than against a stand-in that agrees with my assumptions.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from scitex_dev._ecosystem._process_currency import (
    Currency,
    describe_process_currency,
    newest_package_mtime,
    process_start_time,
)

_HZ = os.sysconf("SC_CLK_TCK")


def _fake_proc(tmp_path: Path, pid: int, *, started_secs_ago: float) -> Path:
    """A /proc tree whose `pid` started `started_secs_ago` seconds ago."""
    proc = tmp_path / "proc"
    (proc / str(pid)).mkdir(parents=True)
    uptime = 100_000.0
    (proc / "uptime").write_text(f"{uptime} {uptime}\n")
    ticks = int((uptime - started_secs_ago) * _HZ)
    # Field 22 is index 19 after the comm field. Pad the preceding fields.
    # 18 zeros: `after_comm[0]` is the state field, so starttime (field 22)
    # lands at index 19 — the same index the parser reads from real /proc.
    fields = ["0"] * 18 + [str(ticks)]
    (proc / str(pid) / "stat").write_text(f"{pid} (python3) S " + " ".join(fields))
    return proc


def _package(tmp_path: Path, *, mtime: float) -> Path:
    root = tmp_path / "pkg"
    root.mkdir()
    f = root / "__init__.py"
    f.write_text("x = 1\n")
    os.utime(f, (mtime, mtime))
    return root


def test_a_process_older_than_its_package_is_flagged(tmp_path):
    """THE POSITIVE CONTROL — the orphan case, planted."""
    # Arrange
    proc = _fake_proc(tmp_path, 4242, started_secs_ago=7200)
    root = _package(tmp_path, mtime=time.time())
    # Act
    result = describe_process_currency(4242, root, proc=proc)
    # Assert
    assert result.verdict is Currency.MAY_BE_STALE


def test_a_process_newer_than_its_package_is_not_flagged(tmp_path):
    """THE NEGATIVE CONTROL — a screen that flags everything is not a screen."""
    # Arrange
    proc = _fake_proc(tmp_path, 4243, started_secs_ago=1)
    root = _package(tmp_path, mtime=time.time() - 7200)
    # Act
    result = describe_process_currency(4243, root, proc=proc)
    # Assert
    assert result.verdict is Currency.CURRENT


def test_an_unreadable_proc_is_unknown_not_current(tmp_path):
    """"I could not look" must never render as "it is fine"."""
    # Arrange
    proc = tmp_path / "proc"
    proc.mkdir()
    root = _package(tmp_path, mtime=time.time())
    # Act
    result = describe_process_currency(9999, root, proc=proc)
    # Assert
    assert result.verdict is Currency.UNKNOWN


def test_a_package_with_no_python_files_is_unknown_not_current(tmp_path):
    # Arrange
    proc = _fake_proc(tmp_path, 4244, started_secs_ago=1)
    empty = tmp_path / "empty"
    empty.mkdir()
    # Act
    result = describe_process_currency(4244, empty, proc=proc)
    # Assert
    assert result.verdict is Currency.UNKNOWN


def test_a_comm_field_containing_a_paren_is_parsed_correctly(tmp_path):
    """`(sd-pam)` is a real process name and splitting on whitespace breaks it."""
    # Arrange
    proc = tmp_path / "proc"
    (proc / "77").mkdir(parents=True)
    (proc / "uptime").write_text("100000.0 100000.0\n")
    ticks = int(99_000 * _HZ)
    # 18 zeros: `after_comm[0]` is the state field, so starttime (field 22)
    # lands at index 19 — the same index the parser reads from real /proc.
    fields = ["0"] * 18 + [str(ticks)]
    (proc / "77" / "stat").write_text("77 ((sd-pam)) S " + " ".join(fields))
    # Act
    started = process_start_time(77, proc=proc)
    # Assert
    assert started is not None


def test_the_newest_file_wins_not_the_directory(tmp_path):
    """An in-place edit moves a FILE's mtime and leaves the directory's alone."""
    # Arrange
    root = tmp_path / "pkg"
    (root / "sub").mkdir(parents=True)
    old, new = time.time() - 9000, time.time() - 10
    for path, when in ((root / "a.py", old), (root / "sub" / "b.py", new)):
        path.write_text("x = 1\n")
        os.utime(path, (when, when))
    # Act
    result = newest_package_mtime(root)
    # Assert
    assert result == new


# EOF
