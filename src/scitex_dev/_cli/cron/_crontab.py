#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crontab read/write helpers for `scitex-dev cron`.

The cron CLI manages a set of named jobs (see ``_jobs.JOB_REGISTRY``).
Each managed line is tagged with the marker comment

    # scitex-dev cron: <name>

so that

  * ``install <name>``   — replaces an existing line with the same name
                           (idempotent) and appends if none present.
  * ``remove <name>``    — strips exactly the line(s) with that marker.
  * ``list``             — enumerates managed lines by parsing markers.

All other lines in the user's crontab are preserved verbatim.

Public API
----------
- ``MARKER_PREFIX``        — leading sentinel ``# scitex-dev cron: ``
- ``managed_marker(name)`` — full marker comment for a given job name
- ``build_line(...)``      — pure builder for a managed crontab line
- ``CrontabRead``          — outcome of a read: text + whether it was READABLE
- ``read_crontab_state()`` — read the crontab, distinguishing "empty" from
                             "could not look" (no binary / read error)
- ``read_crontab()``       — current user's crontab as text (``""`` if none)
- ``write_crontab(text)``  — replace the entire crontab from text
- ``parse_managed(text)``  — yield ``(name, schedule, command, raw_line)``
- ``upsert_managed(...)``  — return text with the named line replaced/added
- ``remove_managed(...)``  — return text with the named line(s) removed

The ``read_fn`` / ``write_fn`` parameters on ``install`` / ``remove`` etc.
are dependency-injection seams used by tests so we never need
``unittest.mock`` or ``monkeypatch``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

MARKER_PREFIX = "# scitex-dev cron: "

# Matches a managed crontab line:
#   "<5 schedule fields> <command body> # scitex-dev cron: <name>"
# We don't try to validate the schedule shape — the registry produces it.
_LINE_RE = re.compile(
    r"^(?P<schedule>\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+"
    r"(?P<command>.+?)\s+" + re.escape(MARKER_PREFIX) + r"(?P<name>\S+)\s*$"
)


@dataclass(frozen=True)
class ManagedLine:
    """One ``# scitex-dev cron: <name>`` line parsed from a crontab."""

    name: str
    schedule: str
    command: str
    raw: str


def managed_marker(name: str) -> str:
    """Return the marker comment for a managed job ``name``."""
    if not name or any(c.isspace() for c in name):
        raise ValueError(f"invalid cron job name: {name!r}")
    return f"{MARKER_PREFIX}{name}"


def build_line(name: str, schedule: str, command: str) -> str:
    """Build the single managed crontab line for the given job.

    No quoting is performed on ``command`` — the registry is trusted to
    supply a single-line shell-safe invocation (typically a console
    script path + subcommand).
    """
    if "\n" in command:
        raise ValueError("cron command must not contain newlines")
    return f"{schedule} {command} {managed_marker(name)}"


@dataclass(frozen=True)
class CrontabRead:
    """The outcome of one ``crontab -l`` attempt.

    Three states, deliberately distinct — collapsing the third into the
    second is what made ``cron list`` report a confident "installed (0)"
    from a container that had no ``crontab`` binary at all:

      * ``readable=True``,  ``text`` non-empty — the crontab was read.
      * ``readable=True``,  ``text == ""``     — read fine, genuinely empty.
      * ``readable=False``, ``reason`` set     — we could NOT look. Callers
        must render this as UNKNOWN, never as zero.
    """

    text: str
    readable: bool
    reason: str | None = None


# `crontab -l` exits non-zero for the perfectly ordinary "this user has no
# crontab" case. That IS an empty crontab; anything else non-zero is a
# genuine failure to read.
_NO_CRONTAB_RE = re.compile(r"no crontab for", re.IGNORECASE)


def read_crontab_state(
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> CrontabRead:
    """Read the current user's crontab, reporting readability honestly.

    Read-only paths (``cron list`` / ``cron status`` / any ``*-dry-run``)
    must still WORK in crontab-less environments (CI, containers) — they
    just must not claim to have found zero managed lines there. Writes
    remain loud: ``write_crontab`` raises when the binary is absent, since
    you cannot modify a crontab on a system that has none.
    """
    run = runner or subprocess.run
    try:
        r = run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except FileNotFoundError:
        return CrontabRead("", False, "'crontab' not found on PATH")
    except subprocess.TimeoutExpired:
        return CrontabRead("", False, "'crontab -l' timed out")
    except OSError as exc:
        return CrontabRead("", False, f"'crontab -l' failed: {exc}")
    if r.returncode != 0:
        detail = (r.stderr or "").strip() or (r.stdout or "").strip()
        if _NO_CRONTAB_RE.search(detail):
            return CrontabRead("", True, None)
        return CrontabRead(
            "",
            False,
            f"'crontab -l' exited {r.returncode}"
            + (f": {detail}" if detail else ""),
        )
    return CrontabRead(r.stdout, True, None)


def read_crontab(
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """Return the current user's crontab text (``""`` if none or unreadable).

    Lossy by design, and kept only for callers that genuinely cannot act on
    the difference. Anything that REPORTS to a human or a machine must use
    :func:`read_crontab_state` instead, so "could not look" is never
    rendered as "looked, found nothing".
    """
    return read_crontab_state(runner=runner).text


def write_crontab(
    content: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> None:
    """Replace the current user's crontab with ``content``."""
    run = runner or subprocess.run
    try:
        r = run(
            ["crontab", "-"],
            input=content,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("'crontab' not found on PATH") from exc
    if r.returncode != 0:
        raise RuntimeError(
            f"crontab write failed: {r.stderr.strip() or r.stdout.strip()}"
        )


def parse_managed(text: str) -> list[ManagedLine]:
    """Return every managed line found in ``text`` in source order."""
    out: list[ManagedLine] = []
    for raw in text.splitlines():
        if MARKER_PREFIX not in raw:
            continue
        m = _LINE_RE.match(raw)
        if not m:
            # The marker is present but the rest of the line is ill-formed;
            # surface it with empty schedule/command so `list` can still
            # show the operator that something is off.
            tail = raw.split(MARKER_PREFIX, 1)[1].strip()
            out.append(ManagedLine(name=tail, schedule="", command="", raw=raw))
            continue
        out.append(
            ManagedLine(
                name=m.group("name"),
                schedule=m.group("schedule"),
                command=m.group("command").rstrip(),
                raw=raw,
            )
        )
    return out


def _without_managed(text: str, names: Iterable[str]) -> tuple[str, int]:
    """Return ``(text_without_named_lines, removed_count)``.

    Non-managed lines are preserved verbatim including blank lines and
    comments. The output preserves a trailing newline only if the input
    had one and at least one non-managed line remains.
    """
    targets = {managed_marker(n) for n in names}
    kept: list[str] = []
    removed = 0
    for line in text.splitlines():
        if any(t in line for t in targets):
            removed += 1
            continue
        kept.append(line)
    new = "\n".join(kept)
    if text.endswith("\n") and new:
        new += "\n"
    return new, removed


def upsert_managed(text: str, name: str, schedule: str, command: str) -> str:
    """Return ``text`` with the named managed line replaced or appended."""
    new_line = build_line(name, schedule, command)
    stripped, _ = _without_managed(text, [name])
    body = stripped.rstrip("\n")
    if body:
        return body + "\n" + new_line + "\n"
    return new_line + "\n"


def remove_managed(text: str, name: str) -> tuple[str, int]:
    """Return ``(text_without_name, removed_count)``."""
    return _without_managed(text, [name])


# EOF
