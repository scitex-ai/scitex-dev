#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The engine is gone; this keeps its NAME from coming back.

Operator ruling, 2026-08-29: *「サイテックスデベロップメントの中にスクライトと
言う文字があったら、その時点でバグです」* — if the string appears anywhere in
scitex-dev, that is itself a bug. The one exception is ``docs/adr/``, because
an ADR records a decision that was actually taken and rewriting it would
destroy the record rather than the dependency.

WHY A STRING SCAN AND NOT AN IMPORT CHECK. The previous removal was reverted
in effect, not in commit: the code kept working while the DOCUMENTATION went
on naming a second engine as the default, and a fleet survey then counted 66
of 68 live tables sitting on it. Whoever put them there was following the
prose correctly. A rule that only bans the import leaves the sentence that
does the damage — so this bans the sentence.

The scan is over TRACKED files, via ``git ls-files``: a scratch file, a stray
download or an untracked note is not what ships.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

#: Repo root — this file is ``tests/scitex_dev/<name>.py``.
ROOT = Path(__file__).resolve().parents[2]

#: The only place the name may still appear, and why: an ADR is a record of a
#: decision, not an instruction to a reader.
ALLOWED_PREFIXES = ("docs/adr/",)

#: Generated trees. They are rebuilt from ``src/``, so a hit here is a stale
#: artefact rather than a source of truth — and failing on one sends the
#: reader to delete a build directory instead of fixing anything.
IGNORED_PREFIXES = ("build/", "src/scitex_dev.egg-info/")

#: Files whose meaningful lines are all exclusion rules. A PATTERN naming the
#: engine is a refusal to accept its files — the same shape as this file naming
#: what it bans, and the reason that self-exemption exists. Deleting such a
#: pattern to lower a text count trades a real protection for a cosmetic
#: number: scitex-ssh had 55 committed database files to remove precisely
#: because no rule covered them, and they were binary, so `git grep -I` could
#: not see them either.
#:
#: COMMENTS IN THESE FILES ARE STILL PROSE and are still banned. The exemption
#: is for the rule, not for the file.
IGNORE_RULE_BASENAMES = frozenset(
    {
        ".gitignore",
        ".dockerignore",
        ".npmignore",
        ".prettierignore",
        ".eslintignore",
        ".rgignore",
        ".ignore",
    }
)

_NAME = re.compile(r"sqlite", re.IGNORECASE)


def _is_ignore_pattern(rel: str, line: str) -> bool:
    """Whether ``line`` is an exclusion RULE rather than prose about one."""
    if Path(rel).name not in IGNORE_RULE_BASENAMES:
        return False
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _offenders() -> list[str]:
    hits: list[str] = []
    for rel in _tracked_files():
        if rel.startswith(ALLOWED_PREFIXES) or rel.startswith(IGNORED_PREFIXES):
            continue
        if rel == str(Path(__file__).relative_to(ROOT)):
            continue  # this file names it in order to ban it
        try:
            text = (ROOT / rel).read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - binary/unreadable
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not _NAME.search(line):
                continue
            if _is_ignore_pattern(rel, line):
                continue
            hits.append(f"{rel}:{number}: {line.strip()[:110]}")
    return hits


def test_the_scan_can_actually_find_the_name(tmp_path):
    """Positive control: a scan that cannot fail is not a scan.

    Without this, a broken ``git ls-files`` or an over-eager filter would
    return zero offenders and read exactly like success.
    """
    # Arrange
    probe = "SQLite"
    # Act
    found = _NAME.search(f"a line mentioning {probe} in passing")
    # Assert
    assert found is not None


def test_the_tracked_file_list_is_not_empty():
    """Second control: the scan must have had something to look at."""
    # Arrange
    # Act
    tracked = _tracked_files()
    # Assert
    assert len(tracked) > 100


def test_an_ignore_rule_may_name_what_it_excludes():
    """A pattern in a `.gitignore` is a refusal, not a mention.

    Deleting one to lower a text count trades a real protection for a
    cosmetic number — scitex-ssh had 55 committed database files to remove
    precisely because no rule covered them, and being binary they were
    invisible to ``git grep -I`` as well.
    """
    # Arrange
    pattern = "**/*.sqlite"
    # Act
    exempt = _is_ignore_pattern(".gitignore", pattern)
    # Assert
    assert exempt is True


def test_a_comment_in_an_ignore_file_is_still_prose():
    """The exemption is for the RULE, not for the file.

    This is the control that stops the previous test from being a hole:
    if `.gitignore` were exempt wholesale, prose could hide in it.
    """
    # Arrange
    comment = "# sqlite was retired on 2026-08-29"
    # Act
    exempt = _is_ignore_pattern(".gitignore", comment)
    # Assert
    assert exempt is False


def test_the_exemption_does_not_leak_to_ordinary_files():
    """A second control: the same pattern text is NOT exempt elsewhere."""
    # Arrange
    pattern = "**/*.sqlite"
    # Act
    exempt = _is_ignore_pattern("src/scitex_dev/store/_store.py", pattern)
    # Assert
    assert exempt is False


def test_no_tracked_file_outside_an_adr_names_the_retired_engine():
    # Arrange — source, tests and documentation must reach zero.
    # Act
    offenders = _offenders()
    # Assert
    assert offenders == [], (
        f"{len(offenders)} tracked file(s) still name the retired engine. "
        "Only docs/adr/ may:\n" + "\n".join(offenders[:40])
    )

# EOF
