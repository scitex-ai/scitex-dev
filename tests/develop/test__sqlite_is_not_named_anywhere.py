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

abolition-guard: detector — this file names the engine in order to forbid it,
and declares that with the same marker any other detector uses. It used to be
exempted by a path comparison against its own ``__file__``, which made the
guard a special case instead of an instance of its own rule; a detector in
another repository could not say the same thing about itself.
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

#: Generated Sphinx output, ignored by PATH SEGMENT rather than prefix because
#: it lives under the package — `src/<pkg>/_sphinx_html/` — not at the root.
#:
#: This is not a courtesy. A doctree pickle embeds Sphinx's intersphinx
#: inventory, which carries CPython's own documentation URLs, so
#: `docs.python.org/3/library/sqlite3.html` appears there no matter what this
#: project writes. Measured across the fleet: scitex-dict and
#: scitex-notification each hold 491 matches in `environment.pickle`, ALL 491
#: adjacent to that URL. scitex-dev itself tracks 92 files under these
#: directories.
#:
#: So a guard without this fails on arrival in any repo that ships built docs,
#: and fails on something no author wrote and no rewrite can remove — a
#: rebuild re-adds every one. Worse, rebuilding inside a worktree bakes the
#: BUILD PATH into tracked binaries, so a branch named after the thing being
#: removed writes it into files `git grep -I` cannot even see.
IGNORED_PATH_SEGMENTS = ("_sphinx_html/", ".doctrees/")

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

#: A file may DECLARE ITSELF a detector by carrying this marker. A rule that
#: forbids the engine has to name it to match it, and that is true wherever the
#: rule lives — this file's own path-based self-exemption was the special case,
#: not the principle.
#:
#: Verified in scitex-io: rule IO015 forbids ``sqlite3.connect()`` and was
#: measured FIRING against a real probe (``W …:2:7 STX-IO015``), not merely
#: present in a rule table. Deleting it to lower a count would have removed a
#: protection against the thing being eradicated.
#:
#: The marker is deliberately self-certifying and deliberately GREPPABLE: it
#: cannot stop someone exempting prose, but it cannot be done quietly either —
#: it appears in the diff, and `git grep` finds every claim in one command. An
#: exemption nobody can enumerate is the failure this whole effort is about.
#:
#: Note it does NOT contain the banned word, so declaring a detector never adds
#: to the count it exempts.
DETECTOR_MARKER = "abolition-guard: detector"

_NAME = re.compile(r"sqlite", re.IGNORECASE)


def _declares_itself_a_detector(text: str) -> bool:
    """Whether the file claims to name the engine in order to forbid it."""
    return DETECTOR_MARKER in text


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
        if any(seg in rel for seg in IGNORED_PATH_SEGMENTS):
            continue
        try:
            text = (ROOT / rel).read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - binary/unreadable
            continue
        # A detector names the engine in order to forbid it. This file is one,
        # and says so with the same marker any other detector uses rather than
        # by being special-cased on its path.
        if _declares_itself_a_detector(text):
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


def test_a_file_may_declare_itself_a_detector():
    """A rule that forbids the engine has to name it to match it.

    Verified in scitex-io, not assumed: rule IO015 forbids
    ``sqlite3.connect()`` and was measured firing against a real probe.
    """
    # Arrange
    body = f"# {DETECTOR_MARKER}\nBANNED = re.compile('sqlit' + 'e')\n"
    # Act
    declared = _declares_itself_a_detector(body)
    # Assert
    assert declared is True


def test_an_ordinary_file_declares_nothing():
    """The control: without the marker, a file is not exempt.

    Without this, the previous test would pass against a predicate that
    returned True unconditionally.
    """
    # Arrange
    body = "def load(path):\n    return open(path)\n"
    # Act
    declared = _declares_itself_a_detector(body)
    # Assert
    assert declared is False


def test_this_guard_declares_itself_rather_than_being_special_cased():
    """The guard is an instance of its own rule, not an exception to it.

    It was exempted by comparing ``__file__`` against the scanned path, which
    is a privilege no detector in another repository could claim.
    """
    # Arrange
    own_text = Path(__file__).read_text()
    # Act
    declared = _declares_itself_a_detector(own_text)
    # Assert
    assert declared is True


def test_the_marker_does_not_itself_name_the_engine():
    """Declaring a detector must not add to the count it exempts."""
    # Arrange
    marker = DETECTOR_MARKER
    # Act
    names_it = _NAME.search(marker)
    # Assert
    assert names_it is None


def test_generated_sphinx_output_is_ignored_by_segment_not_prefix():
    """It lives under the package, so a prefix check would miss it.

    `src/scitex_dict/_sphinx_html/.doctrees/environment.pickle` starts with
    `src/`, not with any ignorable prefix.
    """
    # Arrange
    rel = "src/scitex_dict/_sphinx_html/.doctrees/environment.pickle"
    # Act
    ignored = any(seg in rel for seg in IGNORED_PATH_SEGMENTS)
    # Assert
    assert ignored is True


def test_an_ordinary_source_path_is_not_ignored():
    """The control: the segment check must not swallow real source."""
    # Arrange
    rel = "src/scitex_dev/store/_store.py"
    # Act
    ignored = any(seg in rel for seg in IGNORED_PATH_SEGMENTS)
    # Assert
    assert ignored is False


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
