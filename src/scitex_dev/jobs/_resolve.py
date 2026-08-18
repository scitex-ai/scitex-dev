#!/usr/bin/env python3
"""Resolve HOW and WHEN a job runs, independent of unit text.

Split out of ``_systemd.py`` so that file holds one responsibility —
rendering unit TEXT — and this one holds the other: turning a schedule
into a cadence and a command into an absolute ``ExecStart``. The
dependency runs one way only, ``_systemd`` -> ``_resolve``.

The functions were moved verbatim; no behaviour changed. ``_systemd``
re-exports every name below, so existing imports keep working.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import warnings
from pathlib import Path

#: Defaults for a job that does not state its own cadence. They live here
#: rather than in ``_systemd`` because they are inputs to the DERIVATION,
#: and keeping them beside it is what makes the import one-directional.
DEFAULT_ON_BOOT_SEC = "15min"
DEFAULT_ON_UNIT_ACTIVE_SEC = "1h"


def derive_on_unit_active_sec(schedule: str) -> str:
    """Derive an ``OnUnitActiveSec`` from a 5-field cron ``schedule``.

    Best-effort: this is only used when a job declares no explicit
    ``on_unit_active_sec``. We read the minute and hour fields and map a
    handful of common ``*/N`` step forms to a duration; anything we
    don't recognise falls back to ``DEFAULT_ON_UNIT_ACTIVE_SEC``.
    """
    fields = schedule.split()
    if len(fields) != 5:
        return DEFAULT_ON_UNIT_ACTIVE_SEC
    minute, hour = fields[0], fields[1]

    # "*/N * * * *"  -> every N minutes
    if minute.startswith("*/") and hour == "*":
        n = _safe_int(minute[2:])
        if n:
            return f"{n}min"
    # "M */N * * *"  -> every N hours
    if hour.startswith("*/"):
        n = _safe_int(hour[2:])
        if n:
            return f"{n}h"
    # "M H * * *"    -> a fixed daily time
    if minute.isdigit() and hour.isdigit():
        return "1d"
    return DEFAULT_ON_UNIT_ACTIVE_SEC


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def _on_boot_sec_to_seconds(value: str) -> int:
    """Best-effort parse of a systemd duration string into integer seconds.

    Recognises the small set of suffixes we actually use
    (``s`` / ``min`` / ``h``). Anything we don't recognise returns
    ``0`` so ``ExecStartPre=/bin/sleep 0`` is a harmless no-op rather
    than a unit-write failure.
    """
    text = value.strip().lower()
    if text.endswith("min"):
        n = _safe_int(text[:-3])
        return (n or 0) * 60
    if text.endswith("h"):
        n = _safe_int(text[:-1])
        return (n or 0) * 3600
    if text.endswith("s"):
        n = _safe_int(text[:-1])
        return n or 0
    n = _safe_int(text)
    return n or 0


def _interpreter_bindir(executable: str | None = None) -> Path:
    """Return ``Path(sys.executable).parent`` — the bin/ holding sibling
    console scripts for the interpreter currently running this process.

    NOT ``.resolve()``d, and that is the whole point. A venv's
    ``bin/python`` is a SYMLINK to the interpreter it was built from,
    which lives outside the venv and has no console scripts beside it::

        ~/.venv/bin/python
          -> ~/.local/share/uv/python/cpython-3.12-.../bin/python3.12

    Resolving therefore walks OUT of the venv and lands in a directory
    that structurally cannot hold ``scitex-dev``. Measured on
    scitex-compute-04 2026-08-17: raw parent contained the binary,
    resolved parent did not, so rule 1 missed and the supervisor unit
    was written ``ExecStart=/usr/bin/env scitex-dev`` — the exact
    status=127 flap this function exists to prevent. uv builds every
    venv this way, and uv is now the mandated installer, so the
    resolved form is wrong on essentially every host.

    Resolving buys nothing in the non-venv case either: when
    ``bin/python`` is a real file (or a symlink inside the same dir),
    the resolved and unresolved parents are identical. The two differ
    ONLY when resolving leaves the venv, which is exactly when the
    resolved answer is wrong. So there is no second probe — dropping
    ``.resolve()`` is the whole fix.

    ``executable`` defaults to :data:`sys.executable` and exists so a
    test can point at a REAL venv-shaped tree it built on disk —
    symlink and all — instead of rewriting this module's globals.
    """
    return Path(executable or sys.executable).parent


def resolve_execstart(
    command: str,
    *,
    venv: str | None = None,
    which=shutil.which,
    interpreter_bindir=_interpreter_bindir,
) -> str:
    """Return an ``ExecStart=`` value with the first token absolutised.

    systemd ``--user`` services run under a deliberately minimal PATH
    (``/usr/local/bin:/usr/bin:/bin``) that excludes the operator's
    Python venv and most ecosystem installs. If we emit a relative
    command name like ``scitex-todo board --port 8051`` the unit fails
    to start with ``status=127/EXEC`` (command not found) and any
    leaf service silently flaps.

    Resolution rules (tried in order — first match wins):

    0. **Per-job venv pin** — ``Path(venv) / "bin" / head`` when
       ``venv`` is given (typically ``JobSpec.venv``). "Leaf owns its
       own venv": a cross-package supervised child should resolve
       against ITS OWN venv, not the supervisor's. Takes priority over
       every other rule below. Falls through to them if the pinned
       venv doesn't actually contain the binary (e.g. a stale pin) so
       a misconfigured pin degrades to the old behavior instead of a
       hard failure.
    1. **Interpreter sibling-bin** — ``Path(sys.executable).parent / head``.
       The process that *writes* the unit is the same interpreter that
       installed the console scripts. Its sibling ``bin/`` therefore
       reliably holds ``scitex-todo``, ``scitex-dev``, ``sac``, etc.,
       even when ``ecosystem up`` was invoked via the venv's absolute
       interpreter (no ``activate``) and so the ambient PATH lacks
       the venv's ``bin/`` (the live bug observed on ywata-note-win,
       where ``scitex-todo.wake-watcher.service`` was written with
       ``ExecStart=/usr/bin/env scitex-todo`` and crash-looped at
       ``status=127`` for ~12 h because systemd user PATH lacks
       ``~/.env-3.11/bin``).
    2. **PATH lookup** — :func:`shutil.which` against the ambient PATH.
       Catches operator binaries installed outside the interpreter's
       bin (``/usr/local/bin/...``, ``~/.local/bin/...``, etc.).
    3. **/usr/bin/env fallback** — last resort. Emits a *loud*
       :class:`UserWarning` so the bring-up log makes it obvious the
       resolution missed; the unit will still fail to start with
       ``status=127`` under systemd's minimal PATH, but the operator
       has a breadcrumb.

    Pass-throughs:

    * If the first token is already absolute (starts with ``/``), pass
      through unchanged — the leaf has been explicit.
    * Empty ``command`` returns ``command`` verbatim.

    Args/tokens are preserved verbatim via ``shlex``-style splitting
    + re-joining so a quoted arg with spaces survives the round-trip.

    The ``which`` and ``interpreter_bindir`` keywords are test seams
    (fake-callables); the production defaults are :func:`shutil.which`
    and :func:`_interpreter_bindir`.
    """
    tokens = shlex.split(command)
    if not tokens:
        return command
    head, *tail = tokens
    if head.startswith("/"):
        return command

    # 0. Per-job venv pin — highest priority. The leaf DECLARED which
    #    venv owns this command; trust that over the supervisor's own
    #    interpreter or ambient PATH.
    if venv:
        pinned = Path(venv) / "bin" / head
        if pinned.is_file() and os.access(pinned, os.X_OK):
            return shlex.join([str(pinned), *tail])

    # 1. Interpreter sibling-bin probe — most reliable for console
    #    scripts installed alongside the running interpreter. Probed
    #    UNRESOLVED (the venv's own bin/, where the console scripts
    #    live) — see _interpreter_bindir for why resolving breaks this.
    try:
        candidate = interpreter_bindir() / head
    except Exception:  # pragma: no cover — defensive only
        candidate = None
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return shlex.join([str(candidate), *tail])

    # 2. PATH lookup.
    resolved = which(head)
    if resolved:
        return shlex.join([resolved, *tail])

    # 3. Fallback — emit a LOUD warning so a bring-up log makes the
    #    miss obvious. systemd will still fail with exec=127, but
    #    the operator has a clear breadcrumb instead of a silent flap.
    warnings.warn(
        f"resolve_execstart: could not resolve {head!r} via "
        f"sys.executable's bin ({Path(sys.executable).parent}) nor PATH; "
        f"falling back to '/usr/bin/env {head}'. The systemd user unit "
        f"will likely fail with status=127 because user PATH is minimal. "
        f"Install the binary in the interpreter's bin/ or on PATH before "
        f"running 'ecosystem up'.",
        UserWarning,
        stacklevel=2,
    )
    return f"/usr/bin/env {command}"

