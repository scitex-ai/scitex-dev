#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_warn.py

"""The every-invocation warning + warn-once emission.

Operator, 2026-07-14: "Comments and READMEs are meaningless if nobody reads
them. If you're not on the latest version, that itself should emit a warning.
When I type the command and a newer version is already published, a warning
should appear. THAT is how I learn I need to install."

So the control lives where the attention already is — in front of the command
the operator types every day — not in a document, a dashboard or a tab.

THREE RULES THIS MODULE CANNOT BREAK
------------------------------------
1. **Never slow the CLI down.** No network, no subprocess, no heavy import.
   One small JSON read of a file the refresher already wrote.
   ``<PREFIX>_QUIET`` is honoured before we even touch the disk.
2. **Never break the CLI.** Every failure path ends in silence. A staleness
   warning that can crash the CLI is infinitely worse than the staleness it
   reports.
3. **Never cry wolf.** Only a cached finding that is positively STALE speaks.
   Missing / expired / corrupt cache, unparseable version, offline refresher
   -> UNKNOWN -> **say nothing at all**.

Rules 2 and 3 are why this is a warning and not a hard failure by default.
``<PREFIX>_SEVERITY=error`` is the single knob that tightens it, once the
signal has earned that trust.
"""

from __future__ import annotations

import os
import sys

__all__ = ["EXIT_STALE", "SEVERITY_DEFAULT", "emit_once", "warn_if_stale", "warning_lines"]

SEVERITY_DEFAULT = "warn"
_SEVERITIES = ("silent", "warn", "error")

# Exit code used only when severity=error. Distinct from click's 1/2 so a
# staleness abort is never mistaken for a usage error or a command failure.
EXIT_STALE = 3

_BAR = "!" * 72

# Cross-process warn-once marker: set after the first emit so every
# subprocess inherits the suppression instead of re-printing the banner N
# times. Parameterised per leaf so two leaves do not silence each other.
_EMIT_MARKER_TMPL = "_{prefix}_EMITTED"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def severity(config) -> str:
    """``silent`` | ``warn`` (default) | ``error``.

    An unrecognised value falls back to the default instead of raising — a
    typo in an env var must never be able to break the CLI.
    """
    raw = (os.environ.get(config.env_severity) or "").strip().lower()
    return raw if raw in _SEVERITIES else SEVERITY_DEFAULT


def warning_lines(config, findings) -> list[str]:
    """The banner. Every stale finding gets its own summary + fix pair.

    An alarm that does not say what to DO is one people learn to skip.
    """
    if not findings:
        return []
    lines = [
        _BAR,
        f"{config.dist}: version-currency WARNING — this is not what shipped.",
    ]
    for finding in findings:
        lines.append(f"  * {finding.summary}")
        if finding.remedy:
            lines.append(f"      fix: {finding.remedy}")
    lines.append(f"  (silence: {config.env_quiet}=1)")
    lines.append(_BAR)
    return lines


def warn_if_stale(config, stream=None) -> int:
    """Emit the staleness banner to stderr. Returns an exit code.

    Returns ``0`` in every case except ``severity=error`` with a genuinely
    STALE cached report, which returns :data:`EXIT_STALE`. This function's own
    contract is that it NEVER raises, whatever it finds on disk.

    ``stream`` is resolved at call time (default ``sys.stderr``) so tests can
    capture it.
    """
    if _truthy(os.environ.get(config.env_quiet)):
        return 0
    level = severity(config)
    if level == "silent":
        return 0

    debug = _truthy(os.environ.get(config.env_debug))
    out = stream if stream is not None else sys.stderr

    try:
        from ._cache import read_cache

        report = read_cache(config)
        if report is None:
            if debug:
                print(
                    f"{config.dist}-currency: no usable cache "
                    "(missing/expired/corrupt) -> UNKNOWN -> silent.",
                    file=out,
                )
            return 0

        stale = report.stale
        if not stale:
            if debug:
                print(
                    f"{config.dist}-currency: cached state="
                    f"{report.state.value} -> nothing to warn about",
                    file=out,
                )
            return 0

        for line in warning_lines(config, stale):
            print(line, file=out)
        return EXIT_STALE if level == "error" else 0

    except Exception as exc:  # noqa: BLE001 - rule 2: a warning must NEVER break the CLI; any failure degrades to silence
        if debug:
            print(f"{config.dist}-currency: check failed ({exc!r}) -> silent", file=out)
        return 0


def emit_once(config, stream=None) -> int:
    """Warn-once wrapper over :func:`warn_if_stale`. Safe to call repeatedly.

    Suppression is two-layered so a parent process emits at most once and
    every subprocess inherits the suppression via an env marker instead of
    re-printing the same banner:

    * in-process: a function-attribute flag keyed by ``config.dist``;
    * across processes: ``_<PREFIX>_EMITTED=1``, set after the first call and
      inherited by every subprocess.

    Mirrors ``check_editable_drift.emit_if_drift`` — the warn-once pattern
    scitex-dev already ships.
    """
    seen = getattr(emit_once, "_seen", None)
    if seen is None:
        seen = set()
        emit_once._seen = seen  # type: ignore[attr-defined]

    marker = _EMIT_MARKER_TMPL.format(prefix=config.env_prefix)
    if config.dist in seen or os.environ.get(marker) == "1":
        seen.add(config.dist)
        os.environ[marker] = "1"
        return 0

    seen.add(config.dist)
    code = warn_if_stale(config, stream=stream)
    os.environ[marker] = "1"
    return code


# EOF
