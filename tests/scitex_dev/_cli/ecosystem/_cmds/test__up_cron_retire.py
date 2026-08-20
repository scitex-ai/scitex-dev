#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._cli.ecosystem._cmds._up_cron_retire.

Cron is retired for SciTeX periodic jobs (ADR-0012): they run in the
supervisor's PeriodicRunner. `ecosystem up` therefore REMOVES the managed
crontab block rather than writing it.

No mocks. The crontab is reached through two seams that these tests
replace with real in-memory functions, so every assertion runs the real
`strip_block` over real crontab text.
"""

from __future__ import annotations

import scitex_dev._cli.cron._crontab as _crontab
from scitex_dev._cli.ecosystem._cmds._up_cron_retire import retire_cron_block
from scitex_dev.jobs._cron_block import BLOCK_BEGIN, BLOCK_END

_FOREIGN = "0 3 * * * /usr/bin/backup.sh"
_MANAGED = (
    f"{BLOCK_BEGIN}\n"
    "*/15 * * * * /bin/echo a # scitex-dev:a\n"
    "*/30 * * * * /bin/echo b # scitex-dev:b\n"
    f"{BLOCK_END}"
)


class _Crontab:
    """A real read/write pair over an in-memory string. Not a mock."""

    def __init__(self, text: str):
        self.text = text
        self.writes: list[str] = []

    def install(self, monkey_free_module) -> None:
        monkey_free_module.read_crontab = self._read
        monkey_free_module.write_crontab = self._write

    def _read(self) -> str:
        return self.text

    def _write(self, new: str) -> None:
        self.writes.append(new)
        self.text = new


def _with_crontab(text: str) -> _Crontab:
    """Point the module's seams at an in-memory crontab, restoring after."""
    fake = _Crontab(text)
    fake._orig_read = _crontab.read_crontab
    fake._orig_write = _crontab.write_crontab
    _crontab.read_crontab = fake._read
    _crontab.write_crontab = fake._write
    return fake


def _restore(fake: _Crontab) -> None:
    _crontab.read_crontab = fake._orig_read
    _crontab.write_crontab = fake._orig_write


def test_a_managed_block_is_removed_with_yes():
    # Arrange
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        removed = retire_cron_block(yes=True, echo=lambda _s: None)
    finally:
        _restore(fake)
    # Assert
    assert removed == 4


def test_the_foreign_line_survives():
    # Arrange — scitex-dev owns the managed block and nothing else.
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        retire_cron_block(yes=True, echo=lambda _s: None)
        final = fake.text
    finally:
        _restore(fake)
    # Assert
    assert _FOREIGN in final


def test_the_managed_marker_is_gone():
    # Arrange
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        retire_cron_block(yes=True, echo=lambda _s: None)
        final = fake.text
    finally:
        _restore(fake)
    # Assert
    assert BLOCK_BEGIN not in final


def test_without_yes_nothing_is_written():
    # Arrange — the removal is destructive, so it needs the same
    # confirmation installing did.
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        retire_cron_block(yes=False, echo=lambda _s: None)
        writes = list(fake.writes)
    finally:
        _restore(fake)
    # Assert
    assert writes == []


def test_without_yes_the_pending_removal_is_reported():
    # Arrange
    said: list[str] = []
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        retire_cron_block(yes=False, echo=said.append)
    finally:
        _restore(fake)
    # Assert
    assert any("RETIRED" in line for line in said)


def test_a_host_with_no_managed_block_writes_nothing():
    # Arrange
    fake = _with_crontab(_FOREIGN + "\n")
    # Act
    try:
        retire_cron_block(yes=True, echo=lambda _s: None)
        writes = list(fake.writes)
    finally:
        _restore(fake)
    # Assert
    assert writes == []


def test_a_host_with_no_managed_block_says_so():
    # Arrange — an absent block is the CORRECT state, and saying so
    # keeps it distinguishable from a failed read, which also writes
    # nothing.
    said: list[str] = []
    fake = _with_crontab(_FOREIGN + "\n")
    # Act
    try:
        retire_cron_block(yes=True, echo=said.append)
    finally:
        _restore(fake)
    # Assert
    assert any("no managed block" in line for line in said)


def test_a_host_with_no_managed_block_removes_zero():
    # Arrange
    fake = _with_crontab(_FOREIGN + "\n")
    # Act
    try:
        removed = retire_cron_block(yes=True, echo=lambda _s: None)
    finally:
        _restore(fake)
    # Assert
    assert removed == 0


def test_the_written_text_ends_with_a_newline():
    """`crontab -` REFUSES input that does not end with a newline.

    MEASURED on ywata-note-win 2026-08-20: the retirement failed on the
    ONLY host that had a managed block -- "new crontab file is missing
    newline before EOF, can't install", 37 lines left in place -- while
    four other hosts reported success, because they had no block and
    returned before ever reaching the writer.

    The tests above assert on the resulting TEXT and never on what is
    handed to `crontab`, so an in-memory writer accepts what the real one
    rejects. This one asserts on the argument.
    """
    # Arrange
    fake = _with_crontab(_FOREIGN + "\n" + _MANAGED + "\n")
    # Act
    try:
        retire_cron_block(yes=True, echo=lambda _s: None)
        written = fake.writes[-1]
    finally:
        _restore(fake)
    # Assert
    assert written.endswith("\n")

# EOF
